-- The fully unlabeled Records
SELECT location_id,
       rgb_core_path IS NOT NULL AS has_rgb,
       swir_core_path IS NOT NULL AS has_swir,
       triage_verdict,
       image_quality_limited,
       COUNT(*) AS n
FROM observations
WHERE water_extent_status IS NULL AND agriculture_present IS NULL
GROUP BY location_id, has_rgb, has_swir, triage_verdict, image_quality_limited
ORDER BY location_id