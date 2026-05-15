import os
from langchain_openai import ChatOpenAI

def get_llm(model_name: str, temperature: float = 0.1):
    """Returns an LLM instance configured for either cloud Gemini or local LM Studio."""
    if "gemini" in model_name.lower():
        # Ensure model name doesn't have redundant 'models/' prefix
        clean_model = model_name.replace("models/", "")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=clean_model,
                temperature=temperature,
                google_api_key=os.getenv("GOOGLE_API_KEY")
            )
        except ImportError:
            # Fallback to OpenAI-compatible endpoint if package not installed
            return ChatOpenAI(
                model=model_name,
                temperature=temperature,
                api_key=os.getenv("GOOGLE_API_KEY"),
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
    else:
        # Default to LM Studio local setup
        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY", "lm-studio"),
            base_url=os.getenv("OPENAI_API_BASE", "http://127.0.0.1:1234/v1")
        )
