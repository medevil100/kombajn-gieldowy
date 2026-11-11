# Zachowanie kolorów raportów historycznych — 11 listopada 2026

Właściciel po pierwszym wdrożeniu nie widział kolorów. W izolowanym,
działającym Streamlit odtworzono wygaszanie wszystkich kolorów dla raportu
starszego niż 20 minut. To błąd prezentacji: stara migawka nadal ma swoje
poprawne relacje między ceną a wskaźnikami.

Poprawka zachowuje te relacje kolorystyczne niezależnie od wieku poprawnie
datowanej migawki. Raport starszy niż 20 minut ma jawny nagłówek:
„Zapis historyczny — kolory opisują sytuację w chwili tego odczytu,
nie aktualny rynek”. Brak daty i data przyszła pozostają neutralne.
Nie zmienia żadnej bramki świeżości skanera, AI, orkiestratora ani TOP 5.

Zakres: indicator_view.py i test_indicator_view_20261111.py. KI.py jest
kontrolowany i instalowany bez zmiany zawartości dla istniejącego procesu
kontrolowanego wdrożenia. Pierwszej paczki nie nadpisano.

Test przeglądarkowy działającego Streamlit sprawdza świeży oraz historyczny
raport przy 360, 768 i 1440 px: cztery rzeczywiste kolory CSS, 29 wierszy,
brak przepełnienia poziomego. Bez produkcyjnej bazy i API.

Status: przygotowanie poprawki; wdrożenie VPS niepotwierdzone.
