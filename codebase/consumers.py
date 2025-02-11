import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
import paramiko

class TmuxConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Accept the WebSocket connection
        await self.accept()

        # Start streaming tmux session output
        self.loop_task = asyncio.create_task(self.stream_tmux_session())

    async def disconnect(self, close_code):
        # Stop the streaming task
        if hasattr(self, 'loop_task'):
            self.loop_task.cancel()

    async def stream_tmux_session(self):
        # Replace these details with your server information
        host = "172.206.95.24"
        username = "azureuser"
        pem_key_path = "/Users/aman/Desktop/codebase/codebase/codeknot_dev_key.pem"
        tmux_session_name = "session_01"
        print("Connecting to terminal")
        # Use paramiko to connect to the remote server
        key = paramiko.RSAKey.from_private_key_file(pem_key_path)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(hostname=host, username=username, pkey=key)

            # Attach to tmux session
            command = f"tmux attach-session -t {tmux_session_name}"
            stdin, stdout, stderr = client.exec_command(command)

            while True:
                output = stdout.read(1024)  # Read in chunks
                if output:
                    await self.send(output.decode("utf-8").replace("\n", "\r\n"))
                await asyncio.sleep(0.1)

        except Exception as e:
            await self.send(f"Error: {str(e)}")
        finally:
            client.close()