SELECT observations.location_id, observations.triage_verdict, COUNT(observations.triage_verdict) as "Number of Images" FROM public.observations
WHERE triage_verdict !='fail'
GROUP BY observations.location_id,observations.triage_verdict
ORDER BY observations.location_id ASC 

