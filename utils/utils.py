def normalize_bool(col):
  return col.astype(str).str.strip().str.lower().map({"true": True, "false": False}).fillna(False)
