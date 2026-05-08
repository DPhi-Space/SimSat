SELECT COUNT(*) FILTER (WHERE image_quality_limited = false) AS quality_limited
FROM observations

SELECT location_id, COUNT(image_quality_limited ) AS "No of Records"
FROM observations
WHERE image_quality_limited = true
GROUP BY Location_id