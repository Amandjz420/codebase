from pyngrok import ngrok

ngrok.set_auth_token(token="2sxUkVyWBcOJTBxztO4hpPoxLg7_6Zkt4jcKKA58TCtBYjHmw")
# Establish a tunnel to the local server running on port 3000
public_url = ngrok.connect(3000)
print(f"ngrok tunnel established at {public_url}")

# Keep the script running to maintain the tunnel
try:
    input("Press Enter to exit...\n")
except KeyboardInterrupt:
    print("Shutting down tunnel...")
finally:
    ngrok.disconnect(public_url)