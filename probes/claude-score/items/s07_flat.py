def doubled_positives(records):
    """2×v for each record with a positive 'v'; 0 otherwise."""
    result = []
    for record in records:
        v = (record or {}).get("v")
        result.append(v * 2 if v and v > 0 else 0)
    return result
