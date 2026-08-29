"""
LLM provider abstraction — swap between local Ollama (dev) and Gemini (deployed).
"""
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI

import os

def get_llm(provider: str = "ollama", api_key: str | None = None):
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model="llama3.2", base_url="http://172.31.0.1:11434")

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        key = api_key or os.getenv("GEMINI_API_KEY")
        return ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=key)

    raise ValueError(f"Unknown provider: {provider}")