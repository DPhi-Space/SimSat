SELECT * FROM OBSERVATIONS
WHERE water_extent_status IS NULL
  AND (rgb_core_path IS NULL OR swir_core_path IS NULL)
  AND (triage_verdict IS NULL OR triage_verdict != 'fail')
 