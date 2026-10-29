# KI 2 — usunięcie DeepSeek, 28.10.2026

Pozostał wyłącznie OpenAI w automacie i pytaniach ręcznych. Usunięto endpoint, adaptację JSON, wybory w panelu i odczyt klucza wycofanego dostawcy. Ustawienie analysis_engine zapisano jako openai. Jeżeli lokalny secrets.toml zawierał DEEPSEEK_API_KEY, usunięto ten wpis bez zmiany pozostałych kluczy. Globalnego środowiska Windows i innych projektów nie zmieniano.

Historia i stare raporty pozostają. Ręczne zadanie zapisane dla wycofanego dostawcy nie jest przenoszone do OpenAI ani ponawiane. Nie wykonano ręcznych płatnych wywołań ani wiadomości Telegram. Zmiana nie jest automatycznie commitowana ani pushowana.
