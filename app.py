from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from main import define_graph  # Import your graph setup
from langchain_core.messages import HumanMessage

app = FastAPI()
graph = define_graph()
# Constant thread for local use
config = {"configurable": {"thread_id": "resume-session"}}

class ChatInput(BaseModel):
    message: str

@app.get("/", response_class=HTMLResponse)
async def get():
    return """
    <!DOCTYPE html>
    <html>
        <head><title>Resume AI</title></head>
        <body style="font-family: sans-serif; max-width: 600px; margin: auto; padding: 20px;">
            <div id="chat" style="height: 400px; overflow-y: auto; border: 1px solid #ccc; padding: 10px; margin-bottom: 10px;"></div>
            <input type="text" id="msg" style="width: 80%;" placeholder="Ask something...">
            <button onclick="send()">Send</button>
            <script>
                async function send() {
                    const input = document.getElementById('msg');
                    const chat = document.getElementById('chat');
                    const text = input.value;
                    chat.innerHTML += `<p><b>You:</b> ${text}</p>`;
                    input.value = '';
                    
                    const res = await fetch('/chat', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({message: text})
                    });
                    const data = await res.json();
                    chat.innerHTML += `<p><b>AI:</b> ${data.response}</p>`;
                    chat.scrollTop = chat.scrollHeight;
                }
            </script>
        </body>
    </html>
    """

@app.post("/chat")
async def chat(input_data: ChatInput):
    # Invoke the graph with the message
    result = graph.invoke(
        {"messages": [HumanMessage(content=input_data.message)]}, 
        config=config
    )
    # Get the last message from the updated state
    ai_message = result["messages"][-1].content
    return {"response": ai_message}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)