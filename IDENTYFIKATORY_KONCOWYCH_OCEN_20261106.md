# Osobne identyfikatory końcowych ocen

Naprawa IntegrityError ujawnionego w produkcyjnej bazie dla VYGR i LXRX.
Świeża baza testowa nie zawierała starszego raportu pod identyfikatorem sekwencji;
w produkcji taki raport DONE istniał już od wcześniejszego przebiegu tego dnia.

Nowa końcowa ocena otrzymuje identyfikator zależny od sekwencji i nowej partii.
Oryginalny identyfikator sekwencji nadal łączy ją z matrycą. Stare events,
analysis_jobs, wyniki, odpowiedzi dostawców i potwierdzenia doręczenia pozostają
bez zmian. Wstawienie zadania nie używa już INSERT OR REPLACE.

Matryca zapamiętuje identyfikator ostatniej analizy. Kontrola czasu zakończenia
korzysta z tego odnośnika, a kolejne odczyty go zachowują. Stary raport nie może
przez swój wiek powodować ponownej rezerwacji właśnie zakończonej oceny.

Rezerwację z błędu przygotowania IntegrityError można zwolnić wyłącznie wtedy,
gdy nie powstało żadne zdarzenie tej partii dla tej spółki. Kontrola dotyczy
bieżącej sesji. Zapisuje ślad zwolnienia w historii partii. Nie resetuje zadań
ani research i nie uruchamia dostawcy. Dopiero nowy, zaakceptowany odczyt
skanera może zakwalifikować świeżą ocenę. Istniejące niepewne lub nieudane
wywołania dostawców nie są ponawiane.

Panel odróżnia teraz wybór do przygotowania od rzeczywistego zapisania zadania.
Wyświetla też błąd przygotowania zamiast sugerować, że AI zostało uruchomione.
Komunikat o poprzednim zestawieniu jest widoczny tylko, gdy taki zapis pokazano.

Regresje obejmują bazę z wcześniejszym DONE pod tym samym identyfikatorem,
zachowanie starego raportu, nowe identyfikatory i powiązania, bezpieczne
zwolnienie wyłącznie nieuruchomionej rezerwacji i zachowanie odnośnika po odczycie.
Wszystkie testy działają na tymczasowych bazach, bez prawdziwych zapytań AI/Tavily
i bez prawdziwych wiadomości Telegram.
