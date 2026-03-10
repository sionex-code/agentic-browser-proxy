import asyncio
import json
import os
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from patchright.async_api import async_playwright
import uvicorn
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('request_log.txt'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Global browser and page instances
browser_context = None
page = None
current_chat_url = None
SESSION_LOG_FILE = "session_log.txt"

class Message(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]  # Support both string and array content
    name: Optional[str] = None

class ChatCompletionRequest(BaseModel):
    model: str = "gemini-1.5-pro"
    messages: List[Message]
    stream: Optional[bool] = False
    stream_options: Optional[Dict[str, Any]] = None
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = None
    top_p: Optional[float] = None
    n: Optional[int] = None
    stop: Optional[Union[str, List[str]]] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    user: Optional[str] = None
    store: Optional[bool] = None
    tools: Optional[List[Dict[str, Any]]] = None

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]

# Model context window mapping
MODEL_CONTEXT_WINDOWS = {
    "gemini-pro": 1000000,
    "gemini-1.5-pro": 2000000,
    "gpt-4": 1000000,  # Alias
    "gpt-3.5-turbo": 1000000  # Alias
}

# Load session URL from log file
def load_session_url():
    global current_chat_url
    if os.path.exists(SESSION_LOG_FILE):
        with open(SESSION_LOG_FILE, 'r') as f:
            current_chat_url = f.read().strip()
    return current_chat_url

# Save session URL to log file
def save_session_url(url):
    global current_chat_url
    current_chat_url = url
    with open(SESSION_LOG_FILE, 'w') as f:
        f.write(url)

# Initialize browser
async def init_browser():
    global browser_context, page
    
    if browser_context is None:
        playwright = await async_playwright().start()
        browser_context = await playwright.chromium.launch_persistent_context(
            user_data_dir="session_gemini",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
    
    if page is None:
        page = await browser_context.new_page()
        
        # Load previous session or start new
        session_url = load_session_url()
        if session_url:
            await page.goto(session_url)
        else:
            await page.goto('https://gemini.google.com/')
            print("\n" + "="*60)
            print("PLEASE LOGIN TO GEMINI")
            print("Once logged in and on gemini.google.com/, press ENTER")
            print("="*60 + "\n")
            input("Press ENTER to continue...")
            
            # Save the current URL after login
            current_url = page.url
            save_session_url(current_url)
    
    return page

# Read conversation from page
async def read_conversation():
    js_code = """
    (function() {
      const conversation = [];
      const containers = document.querySelectorAll('.conversation-container');

      containers.forEach(container => {
        const userEl = container.querySelector('.query-text-line');
        const userText = userEl ? userEl.innerText.trim() : null;

        const assistantEl = container.querySelector('model-response .markdown');
        const assistantText = assistantEl ? assistantEl.innerText.trim() : null;

        if (userText) {
          conversation.push({ role: 'user', content: userText });
        }
        if (assistantText) {
          conversation.push({ role: 'assistant', content: assistantText });
        }
      });

      return conversation;
    })();
    """
    
    result = await page.evaluate(js_code)
    return result

# Wait for streaming to complete
async def wait_for_streaming_complete(previous_conversation_length):
    max_wait = 120  # 2 minutes max
    wait_time = 0
    stable_count = 0
    last_content = None
    
    while wait_time < max_wait:
        await asyncio.sleep(1)
        wait_time += 1
        
        conversation = await read_conversation()
        
        # Check if we have new messages
        if len(conversation) > previous_conversation_length:
            current_content = conversation[-1].get('content', '')
            
            # Check if content is stable (not changing)
            if current_content == last_content:
                stable_count += 1
                if stable_count >= 3:  # Content stable for 3 seconds
                    return conversation
            else:
                stable_count = 0
                last_content = current_content
        
        # Check for streaming indicators
        is_streaming = await page.evaluate("""
            () => {
                const streamingIndicators = document.querySelectorAll('.streaming-indicator, .loading-indicator');
                return streamingIndicators.length > 0;
            }
        """)
        
        if not is_streaming and len(conversation) > previous_conversation_length:
            await asyncio.sleep(2)  # Extra wait to ensure completion
            return await read_conversation()
    
    raise TimeoutError("Streaming took too long to complete")

# Send message to Gemini and stream response
async def send_message_streaming(message_text, chunk_queue=None):
    """Send a message to Gemini and stream the response.
    
    If chunk_queue is provided (asyncio.Queue), text chunks are put into it
    in real-time. A None sentinel is put when streaming is complete.
    """
    # Get current conversation before sending
    previous_conversation = await read_conversation()
    previous_length = len(previous_conversation)
    
    # Find and click the textarea
    await page.wait_for_selector('rich-textarea .ql-editor', timeout=10000)
    textarea = await page.query_selector('rich-textarea .ql-editor')
    
    # Clear and type message
    await textarea.click()
    await textarea.fill(message_text)
    await asyncio.sleep(0.5)
    
    # Press Enter to send the message
    await textarea.press('Enter')
    
    # Wait for response to start appearing
    first_content_received = False
    max_wait_for_first = 60  # 60 seconds max to wait for first content
    wait_time = 0
    heartbeat_interval = 3  # Seconds between heartbeats
    last_heartbeat = 0
    
    # Helper: find the last assistant message in conversation
    def get_last_assistant_content(conversation):
        """Find the last assistant message content, ignoring user messages."""
        for msg in reversed(conversation):
            if msg.get('role') == 'assistant':
                return msg.get('content', '')
        return None
    
    # Count assistant messages before sending
    previous_assistant_count = sum(1 for m in previous_conversation if m.get('role') == 'assistant')
    
    # Wait until we get the first assistant content
    while not first_content_received and wait_time < max_wait_for_first:
        await asyncio.sleep(0.5)
        wait_time += 0.5
        
        # Send heartbeat to keep connection alive during Gemini thinking
        if chunk_queue and (wait_time - last_heartbeat) >= heartbeat_interval:
            await chunk_queue.put({"type": "heartbeat"})
            last_heartbeat = wait_time
        
        current_conversation = await read_conversation()
        # Count assistant messages now
        current_assistant_count = sum(1 for m in current_conversation if m.get('role') == 'assistant')
        
        if current_assistant_count > previous_assistant_count:
            current_content = get_last_assistant_content(current_conversation)
            if current_content:  # We have assistant content!
                first_content_received = True
                # Send the first content chunk immediately
                if chunk_queue:
                    await chunk_queue.put({"type": "content", "text": current_content})
                break
    
    if not first_content_received:
        if chunk_queue:
            await chunk_queue.put(None)  # Signal completion
        raise TimeoutError("No response received from Gemini")
    
    # Now stream the response with stability checking
    last_content = current_content if first_content_received else ""
    same_count = 0
    
    while same_count < 3:
        await asyncio.sleep(0.2)
        
        # Read current conversation
        current_conversation = await read_conversation()
        
        # Get the latest assistant message content (ignore user messages)
        current_assistant_count = sum(1 for m in current_conversation if m.get('role') == 'assistant')
        
        if current_assistant_count > previous_assistant_count:
            current_content = get_last_assistant_content(current_conversation)
            if current_content is None:
                current_content = ""
            
            # If content changed, stream the new part
            if current_content != last_content:
                # Send only the new part
                if chunk_queue:
                    new_text = current_content[len(last_content):]
                    await chunk_queue.put({"type": "content", "text": new_text})
                
                last_content = current_content
                same_count = 0  # Reset counter
            else:
                # Content is the same, increment counter
                same_count += 1
    
    # Signal streaming complete
    if chunk_queue:
        await chunk_queue.put(None)
    
    # Final check - get the complete response
    await asyncio.sleep(0.2)
    final_conversation = await read_conversation()
    
    # Protection: Check if conversation actually changed
    final_assistant_count = sum(1 for m in final_conversation if m.get('role') == 'assistant')
    if final_assistant_count <= previous_assistant_count:
        raise Exception("No new message received. Please try again.")
    
    # Save current URL
    current_url = page.url
    save_session_url(current_url)
    
    return final_conversation

# Extract text content from message (handles both string and array formats)
def extract_message_content(content):
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        text_parts = [part.get('text', '') for part in content if isinstance(part, dict) and part.get('type') == 'text']
        return ' '.join(text_parts)
    return str(content)

# Check if we need a new chat
def should_start_new_chat(messages: List[Message], conversation: List[Dict]):
    # If no conversation exists, don't start new (we're already on a fresh page)
    if len(conversation) == 0:
        return False
    
    # Get user messages from both
    user_messages_in_request = [m for m in messages if m.role == "user"]
    user_messages_in_conv = [m for m in conversation if m.get('role') == 'user']
    
    # If request has no user messages, something is wrong
    if len(user_messages_in_request) == 0:
        return False
    
    # If conversation is empty but we have messages to send, use current page
    if len(user_messages_in_conv) == 0:
        return False
    
    # Only start new chat if the FIRST user message is completely different
    # This indicates a new conversation thread
    # Use 'in' check because we may have prepended system instructions
    first_request_content = extract_message_content(user_messages_in_request[0].content).strip()
    first_conv_content = user_messages_in_conv[0].get('content', '').strip()
    
    # If the request's first user message is found within the conversation's first message,
    # it's the same conversation (the page version may have system instructions prepended)
    if first_request_content in first_conv_content or first_conv_content in first_request_content:
        return False
    
    return True

@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    try:
        logger.info(f"Processing chat completion request for model: {request.model}")
        logger.info(f"Number of messages: {len(request.messages)}")
        logger.info(f"Stream mode: {request.stream}")
        
        await init_browser()
        
        # Read current conversation
        current_conversation = await read_conversation()
        
        # Get the last user message to send
        user_messages = [m for m in request.messages if m.role == "user"]
        if not user_messages:
            raise HTTPException(status_code=400, detail="No user message found")
        
        # Extract content using helper function
        last_user_message = extract_message_content(user_messages[-1].content)
        
        # Note: New chat detection disabled - OpenClaw handles session management
        # via /new or /reset commands which send fresh message arrays
        
        # Handle system prompt: always prepend to user message
        # (Gemini has no system role, so we inject it into the user prompt)
        system_messages = [m for m in request.messages if m.role == "system"]
        if system_messages:
            system_content = extract_message_content(system_messages[0].content)
            if system_content:
                last_user_message = f"[System Instructions]\n{system_content}\n\n[User Message]\n{last_user_message}"
                logger.info("System prompt prepended to user message")
        
        # Replace youtube.com with example.com to prevent Gemini from triggering YouTube extension
        last_user_message = last_user_message.replace('youtube.com', 'example.com')
        last_user_message = last_user_message.replace('youtu.be', 'exmpl.be')
        
        logger.info(f"Sending message: {last_user_message[:100]}...")
        
        completion_id = f"chatcmpl-{int(datetime.now().timestamp())}"
        created_time = int(datetime.now().timestamp())
        
        # Handle streaming response
        if request.stream:
            async def generate_stream():
                total_content = ""
                chunk_queue = asyncio.Queue()
                
                # === IMMEDIATELY send the role-only chunk (OpenAI spec) ===
                # This tells the client "I'm alive, response is starting"
                role_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created_time,
                    "model": request.model,
                    "system_fingerprint": "fp_gemini_proxy",
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant", "content": ""},
                        "logprobs": None,
                        "finish_reason": None
                    }]
                }
                yield f"data: {json.dumps(role_chunk)}\n\n"
                
                # Start the streaming task in the background
                async def stream_worker():
                    try:
                        return await send_message_streaming(last_user_message, chunk_queue)
                    except Exception as e:
                        await chunk_queue.put({"type": "error", "error": str(e)})
                        return None
                
                stream_task = asyncio.create_task(stream_worker())
                
                try:
                    # Consume chunks from the queue in real-time
                    while True:
                        try:
                            # Wait for next chunk with a timeout
                            item = await asyncio.wait_for(chunk_queue.get(), timeout=120)
                        except asyncio.TimeoutError:
                            logger.error("Stream queue timed out after 120s")
                            break
                        
                        # None sentinel = streaming is done
                        if item is None:
                            break
                        
                        item_type = item.get("type")
                        
                        if item_type == "heartbeat":
                            # SSE comment to keep connection alive (ignored by SSE clients)
                            yield ": heartbeat\n\n"
                        
                        elif item_type == "content":
                            new_text = item["text"]
                            # Restore youtube.com URLs in response
                            new_text = new_text.replace('example.com', 'youtube.com')
                            new_text = new_text.replace('exmpl.be', 'youtu.be')
                            total_content += new_text
                            
                            content_chunk = {
                                "id": completion_id,
                                "object": "chat.completion.chunk",
                                "created": created_time,
                                "model": request.model,
                                "system_fingerprint": "fp_gemini_proxy",
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": new_text},
                                    "logprobs": None,
                                    "finish_reason": None
                                }]
                            }
                            yield f"data: {json.dumps(content_chunk)}\n\n"
                        
                        elif item_type == "error":
                            logger.error(f"Streaming error: {item['error']}")
                            error_chunk = {
                                "id": completion_id,
                                "object": "chat.completion.chunk",
                                "created": created_time,
                                "model": request.model,
                                "system_fingerprint": "fp_gemini_proxy",
                                "choices": [{
                                    "index": 0,
                                    "delta": {},
                                    "logprobs": None,
                                    "finish_reason": "stop"
                                }]
                            }
                            yield f"data: {json.dumps(error_chunk)}\n\n"
                            yield "data: [DONE]\n\n"
                            return
                    
                    # Wait for the task to complete and get result
                    await stream_task
                    
                    # Send final stop chunk
                    final_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created_time,
                        "model": request.model,
                        "system_fingerprint": "fp_gemini_proxy",
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "logprobs": None,
                            "finish_reason": "stop"
                        }]
                    }
                    yield f"data: {json.dumps(final_chunk)}\n\n"
                    
                    # Send usage info if requested
                    if request.stream_options and request.stream_options.get('include_usage'):
                        prompt_tokens = len(last_user_message.split())
                        completion_tokens = len(total_content.split())
                        usage_chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created_time,
                            "model": request.model,
                            "system_fingerprint": "fp_gemini_proxy",
                            "choices": [],
                            "usage": {
                                "prompt_tokens": prompt_tokens,
                                "completion_tokens": completion_tokens,
                                "total_tokens": prompt_tokens + completion_tokens
                            }
                        }
                        yield f"data: {json.dumps(usage_chunk)}\n\n"
                    
                    yield "data: [DONE]\n\n"
                    
                except Exception as e:
                    logger.error(f"Streaming error: {str(e)}")
                    error_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created_time,
                        "model": request.model,
                        "system_fingerprint": "fp_gemini_proxy",
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "logprobs": None,
                            "finish_reason": "stop"
                        }]
                    }
                    yield f"data: {json.dumps(error_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
            
            headers = {
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",
                headers=headers
            )
        
        # Non-streaming response
        updated_conversation = await send_message_streaming(last_user_message)
        
        # Get the assistant's response (last message)
        if not updated_conversation or len(updated_conversation) == 0:
            raise HTTPException(status_code=500, detail="No response from Gemini")
        
        assistant_message = updated_conversation[-1]
        if assistant_message.get('role') != 'assistant':
            raise HTTPException(status_code=500, detail="Expected assistant response")
        
        assistant_content = assistant_message.get('content', '')
        # Restore youtube.com URLs in response
        assistant_content = assistant_content.replace('example.com', 'youtube.com')
        assistant_content = assistant_content.replace('exmpl.be', 'youtu.be')
        logger.info(f"Received response: {assistant_content[:100]}...")
        
        # Non-streaming response
        response = ChatCompletionResponse(
            id=completion_id,
            created=created_time,
            model=request.model,
            choices=[{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": assistant_content
                },
                "finish_reason": "stop"
            }],
            usage={
                "prompt_tokens": len(last_user_message.split()),
                "completion_tokens": len(assistant_content.split()),
                "total_tokens": len(last_user_message.split()) + len(assistant_content.split())
            }
        )
        
        return response.dict()
        
    except Exception as e:
        logger.error(f"Error in chat_completions: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "gemini-pro",
                "object": "model",
                "created": 1677610602,
                "owned_by": "google",
                "permission": [],
                "root": "gemini-pro",
                "parent": None,
                "context_window": 1000000
            },
            {
                "id": "gemini-1.5-pro",
                "object": "model",
                "created": 1677610602,
                "owned_by": "google",
                "permission": [],
                "root": "gemini-1.5-pro",
                "parent": None,
                "context_window": 2000000
            }
        ]
    }

@app.on_event("startup")
async def startup_event():
    print("\n" + "="*60)
    print("Starting Gemini Proxy API...")
    print("="*60 + "\n")
    await init_browser()
    print("\n" + "="*60)
    print("Browser initialized! API is ready.")
    print("Server running at http://localhost:8000")
    print("="*60 + "\n")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
