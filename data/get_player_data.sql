SELECT 
  py_id,
  firstname, 
  lastname, 
  display_firstname,
  display_lastname,
  concat(date_format(birthday, '%Y-%m-%d'), ' 00:00:00') as birthdate,
  coalesce(nation, Nationality) as nationality,
  case when isGoalie = 1 then 'Goalie' else 'Skater' end as player_position,
  case when fullfacereq = 1 then 'True' else 'False' end as full_face_req,
  'BISHL' as source,
  id_tblPlayer as legacy_id
FROM `tblplayer` 
where dayname(birthday) is not null
ORDER BY firstname, lastname ASC