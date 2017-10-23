SELECT
    msp.TIG_MAP_SET_PARAMETER_NO,
    ms.TIG_MAP_SET_NAME
    || '/'
    || msp.TIG_PARAM_LONG_NAME
FROM
    TIG_MAP_SET ms,
    TIG_MAP_SET_PARAM msp
WHERE
    ms.TIG_MAP_SET_NO = msp.TIG_MAP_SET_NO
    AND(:group_id IS NULL
    OR ms.TIG_MAP_SET_NO = :group_id)
    AND ms.TIG_MAP_SET_TYPE = 4
ORDER BY
    ms.TIG_MAP_SET_NAME,
    msp.TIG_PARAM_LONG_NAME