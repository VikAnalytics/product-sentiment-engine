from google import genai

# Initialize the client exactly as you are doing in your main code
# (e.g., include vertexai=True or project=... if you are using it)
client = genai.Client(api_key="AIzaSyCCpBU9vz_ZaT-9BEjT2qjQ7sXZF-lGu70") 

# List and print models that support embedding
for model in client.models.list():
    if "embed" in model.name.lower():
        print(f"Name: {model.name}")
        print(f"Supported methods: {model.supported_generation_methods}")
        print("-" * 20)