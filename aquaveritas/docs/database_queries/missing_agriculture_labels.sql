
   SELECT
     COUNT(*) FILTER (WHERE image_quality_limited = TRUE) AS quality_limited,
     COUNT(*) FILTER (WHERE rgb_core_path IS NULL OR swir_core_path IS NULL) AS missing_paths,
	 COUNT(*) AS total
   FROM observations