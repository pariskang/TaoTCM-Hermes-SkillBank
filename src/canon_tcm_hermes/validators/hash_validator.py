from canon_tcm_hermes.utils import sha1_text

def content_hash_matches(content: str, content_hash: str) -> bool:
    return sha1_text(content) == content_hash
