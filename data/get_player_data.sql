SELECT 
  py_id,
  firstName, 
  lastName, 
  displayFirstName,
  displayLastName,
  concat(date_format(birthday, '%Y-%m-%d'), ' 00:00:00') as birthdate,
  coalesce(nation, Nationality) as nationality,
  case when isGoalie = 1 then 'Goalie' else 'Skater' end as player_position,
  case when fullfacereq = 1 then 'True' else 'False' end as fullFaceReq,
  'BISHL' as source,
  id_tblPlayer as legacyId
FROM `tblplayer` 
where dayname(birthday) is not null
  and id_tblPlayer >0
ORDER BY firstName, lastName ASC
