SELECT o.id, o.location_id, o.observed_at,
               o.rgb_core_path, o.swir_core_path,
               o.rgb_buffer_path, o.swir_buffer_path,
               o.image_quality_limited,
               o.triage_verdict
        FROM   observations o
        WHERE  o.water_extent_status IS NULL
          AND  o.image_quality_limited IS true
          AND  (o.triage_verdict IS NULL OR o.triage_verdict != 'fail')
        ORDER  BY o.observed_at
        LIMIT  100