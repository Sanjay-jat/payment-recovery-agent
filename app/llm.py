"""
LLM provider abstraction — swap between local Ollama (dev) and Gemini (deployed).
"""

import os


def get_llm(provider: str = "ollama", api_key: str | None = None):
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        host = os.getenv("OLLAMA_HOST_IP", "172.31.0.1")
        return ChatOllama(model="llama3.2", base_url=f"http://{host}:11434", client_kwargs={"timeout": 8.0})

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("No Gemini API key provided")
        return ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=key)

    raise ValueError(f"Unknown provider: {provider}")