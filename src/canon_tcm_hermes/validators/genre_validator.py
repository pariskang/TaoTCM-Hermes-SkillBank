VALID_GENRES = {"canonical_clause","treatise","formula_entry","materia_medica","pulse_text","case_record","commentary","mnemonic_misc","non_medical"}
def is_valid_genre(genre: str) -> bool:
    return genre in VALID_GENRES
