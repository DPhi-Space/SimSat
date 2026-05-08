-- Reset them so they re-enter the queue
UPDATE observations
SET water_extent_status = NULL, flood_risk = NULL, water_clarity = NULL,
    shoreline_encroachment = NULL, agriculture_present = NULL,
    crop_stress_level = NULL, crop_stress_type = NULL,
    cultivation_expanding = NULL, settlement_visible = NULL,
    bare_soil_expansion = NULL, image_quality_limited = NULL
WHERE water_extent_status IS NOT NULL AND agriculture_present IS NULL
  AND (triage_verdict IS NULL OR triage_verdict != 'fail')