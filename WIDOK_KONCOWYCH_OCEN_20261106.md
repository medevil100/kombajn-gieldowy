# Widoczna zakładka końcowych ocen

Dodano osobną zakładkę „Końcowe oceny AI” obok „Automatu”.
Nagłówek jest widoczny także przed pierwszym zestawieniem. Wyświetlany jest stan
oczekiwania albo informacja o wyłączonym trybie lub analizie AI. Otwarcie widoku
tylko odczytuje bazę; nie uruchamia analizy ani wysyłki.

Usunięto też AttributeError dla load_payload przy odświeżeniu fragmentu panelu.
Adapter korzysta z przestrzeni funkcji samego widoku, zamiast z wymienianego
przez Streamlit modułu __main__. Regresja odtwarza zachowany callback i zamianę
tego modułu na pusty, a następnie sprawdza rzeczywiste renderowanie raportu.

Pełne raporty nadal można znaleźć w sekcji końcowych ocen w Automacie.
Raportów sprzed wdrożenia nie przerabiamy na nowe oceny i nie ponawiamy AI.

Poprawka dotyczy wyłącznie widoku i nawigacji. Nie zmienia reguł selekcji,
ustawień, terminów skanowania, limitów, promptów ani danych w bazie.
