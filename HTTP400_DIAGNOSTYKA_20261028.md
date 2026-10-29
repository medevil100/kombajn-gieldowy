# KI 2 — błędy monitora i cytaty, 28.10.2026

Zgłoszenie: LCN.WA i OML.WA miały FAILED z zapisem `OpenAI HTTP 400`. GMT.WA zatrzymano jako REVIEW_REQUIRED z powodu pominięcia częściowego wolumenu, a MUN.WA jako FILTERED bez płatnego AI, ponieważ lokalne dane wystarczały do opisu. To różne przyczyny i nie należy usuwać tych wpisów jako jednego błędu.

## Co wiadomo i czego brakuje

Starszy transport zapisywał wyłącznie kod HTTP, bez typu, parametru i komunikatu odmowy OpenAI. Szczegółu tych dwóch odpowiedzi nie da się odtworzyć z zachowanej bazy. Nie ponowiono historycznych pytań i nie wykonano ręcznej płatnej próby. Sam kod 400 nie dowodzi, że przyczyną jest schemat, limit lub źródło.

Sprawdzono oficjalne wymagania Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat . Dokumentacja dopuszcza enum i gpt-4o-mini. Nie stwierdzono na tej podstawie konkretnej przyczyny odmowy zachowanych żądań.

## Zmiany

- Błędy OpenAI 400/422 zawierają teraz bezpieczny, ograniczony opis: type, code, param, zredagowany komunikat i identyfikator żądania, jeżeli dostawca je zwróci. Nie zapisuje się całego ciała błędu, nagłówka Authorization ani URL; znany klucz i wzorce sekretów są maskowane.
- Ograniczono wybór cytatów do dosłownych fragmentów zawierających potwierdzoną nazwę/alias emitenta. Wykluczono oczywiste fragmenty nawigacji, Image, linki oraz zdania urwane na skrócie S./Sp./Inc./Ltd. Brak odpowiedniego fragmentu pozostawia pustą listę cytatów, bez parafrazy ani zastępczego faktu.
- Ten sam wybór fragmentów trafia do schematu i pakietu danych. Pełne treści nie są obcinane. Zmiana usuwa potwierdzony problem jakości cytatów, ale sama nie jest potwierdzeniem usunięcia HTTP 400.
- Nie dodano automatycznych ponowień, przełączenia dostawcy ani przejścia na słabszy tryb JSON. Baza i historia pozostają zachowane.

## Weryfikacja

Testy sprawdzają zachowanie istotnych danych błędu, redakcję sekretów i URL, limit opisu, wykluczenie bocznych nagłówków oraz dosłowność cytatu emitenta. Testy nie łączą się z płatnymi usługami. Kopie i stan wdrożenia: `backup_20261027_top10/http400-diagnostics-20261028/`.

Dokładna przyczyna HTTP 400 wymaga szczegółu z następnej naturalnej odpowiedzi błędu; ustąpienie problemu wymaga rzeczywistego poprawnego przebiegu. Nie uznaje się samych testów lokalnych za dowód sprawności API.
