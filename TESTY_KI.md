# KI E05 — TESTY

Czytaj najpierw STAN_KI.md.

Jest to wersja uruchomiona 9.10.2026.
SHA-256 KI.py:
C6C045D37389B040117C0BB74D420B3BE2B895CE8B9D96D154FA9B9ED92AD74D

W czystym katalogu repozytorium uruchom:

python -B .\URUCHOM_TESTY_E05_OFFLINE.py

Skrypt sprawdza SHA-256 KI.py i uruchamia 19 grup testowych.
Wynik na Windows wlasciciela: 302 PASS.

Testy nie wywoluja platnych API ani nie wysylaja Telegrama.
Dane SQLite i klucze API musza pozostac poza repozytorium.

Po kazdej poprawce wymagane sa:
- testy poprawianej funkcji,
- pelna regresja,
- kontrola kontraktow i integracji,
- audyt Git staged/unstaged/untracked,
- sprawdzenie braku sekretow i artefaktow.

Dotychczasowy filtr dwoch swiec i limit 3 analiz
nie obowiazuja w E05. Nie przywracac ich.
