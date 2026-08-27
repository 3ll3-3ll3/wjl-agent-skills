# Output schema

Student and faculty certification use the same user-facing field set. Each form field should be in its own copyable code block.

Delivery order after generation:

1. rendered PNG from the actual PPT
2. PPTX
3. Chinese university name
4. Official English Name
5. First name — surname pinyin
6. Last name — given-name pinyin
7. Student ID
8. Address
9. City
10. State/Province
11. Postal/Zip code
12. coordinates last

For faculty mode, the generated numeric ID is written to `{{facultyid}}`, but the compatibility output label remains `Student ID` unless the user explicitly requests `Faculty ID` wording.

Do not output Country/Region, Address line 2, or VAT/GST ID unless explicitly requested.
