import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import List
from fastapi.staticfiles import StaticFiles
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Video Recording Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "video_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/video_uploads", StaticFiles(directory="video_uploads"), name="videos")
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        return len(self.active_connections)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_status(self, websocket: WebSocket, message: str):
        try:
            if websocket in self.active_connections:
                await websocket.send_text(json.dumps({"status": message}))
        except Exception as e:
            logger.error(f"Error sending status: {str(e)}")


manager = ConnectionManager()


@app.get("/")
async def root():
    return {"message": "Video Recording API is running"}


@app.websocket("/ws/video")
async def websocket_endpoint(websocket: WebSocket):
    client_id = str(uuid.uuid4())
    connection_id = await manager.connect(websocket)
    logger.info(f"Client {client_id} connected. Active connections: {connection_id}")
    
    # unique timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{client_id}_{timestamp}.webm"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    with open(filepath, "wb") as video_file:
        try:
            await manager.send_status(websocket, f"Ready to receive video data")
            recording_complete = False
            
            while True:
                # Receive data from WebSocket
                data = await websocket.receive()
                
                # Check if it's binary data (video chunk)
                if "bytes" in data:
                    video_chunk = data["bytes"]
                    video_file.write(video_chunk)
                    logger.debug(f"Received chunk: {len(video_chunk)} bytes")
                
                # Check if it's text data (likely a control message)
                elif "text" in data:
                    message = json.loads(data["text"])
                    if message.get("action") == "complete":
                        logger.info(f"Recording complete for {client_id}")
                        await manager.send_status(websocket, "Recording complete, processing video...")
                        recording_complete = True
                        break
        
        except WebSocketDisconnect:
            logger.info(f"Client {client_id} disconnected")
        except Exception as e:
            logger.error(f"Error processing video stream: {str(e)}")
            await manager.send_status(websocket, f"Error: {str(e)}")
        finally:
            # Only process the video if recording was completed successfully
            if recording_complete:
                # Process the video synchronously before closing the connection
                try:
                    result = await process_video(filepath)
                    await manager.send_status(websocket, 
                        f"Video processing complete. Size: {result['file_size']/1024:.2f} KB. Saved as: {os.path.basename(filepath)}"
                    )
                except Exception as e:
                    logger.error(f"Error processing video: {str(e)}")
                    await manager.send_status(websocket, f"Error processing video: {str(e)}")
            
            # Disconnect the WebSocket after processing is complete
            manager.disconnect(websocket)
            logger.info(f"Connection closed for client {client_id}")


async def process_video(video_path: str):
    """
    Process the recorded video file.
    This is where you would add your video processing logic.
    """
    try:
        logger.info(f"Processing video: {video_path}")
        
        # Simulate processing with a delay
        await asyncio.sleep(2)  # Simulate processing time
        
        # Here you would add your actual video processing code
        # Examples: ffmpeg processing, ML analysis, compression, etc.
        
        # For demonstration, we'll just confirm the file exists and has content
        file_size = os.path.getsize(video_path)
        
        return {"success": True, "file_path": video_path, "file_size": file_size}
    
    except Exception as e:
        logger.error(f"Error processing video: {str(e)}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)