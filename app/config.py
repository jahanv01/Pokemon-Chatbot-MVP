from dotenv import load_dotenv  # exports .env into os.environ for the LLM provider SDKs
from pydantic_settings import BaseSettings, SettingsConfigDict


def load_env(path: str | None = None, override: bool = False) -> None:
    load_dotenv(path, interpolate=False, override=override)  # interpolate=False keeps passwords containing ${...} exactly as typed


load_env()  # so GOOGLE_API_KEY / OPENAI_API_KEY etc. in .env reach init_chat_model and Settings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")  # values come from os.environ (filled by load_env above)

    # provider:model string understood by langchain's init_chat_model
    llm_model: str = "google_genai:gemini-3.5-flash-lite"  # fast Gemini model with a free tier
    llm_fallback_models: str = "google_genai:gemini-3.5-flash"  # comma-separated; tried in order when the main model fails (e.g. daily free quota used up)
    pokeapi_base_url: str = "https://pokeapi.co/api/v2"
    cache_ttl_seconds: int = 3600
    not_found_ttl_seconds: int = 60  # how long a 404 is remembered
    recursion_limit: int = 16
    max_message_chars: int = 1000
    app_access_username: str | None = None  # login name; unset = nobody can log in
    app_access_password: str | None = None  # gate for the whole chat; unset = nobody can log in
    token_ttl_seconds: int = 43200  # login lasts 12 hours

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.llm_fallback_models.split(",") if m.strip()]  # clean list of names


settings = Settings()
