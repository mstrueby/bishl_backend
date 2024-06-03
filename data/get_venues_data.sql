-- get Venues

select
  name,
  replace(
      replace(
          replace(
              replace(  
                  replace(
                      replace(
                          replace(lower(trim(v.name)), ' ', '-')
                          , 'ü', 'ue')
                      , 'ö', 'oe')
                  , 'ä' ,'ae')
              , 'ß', 'ss')
          , '`', '-')
      , '.', '') as alias,
  shortname as shortName,
  addressline1 as street,
  postalcode as zipCode,
  city,
  'Deutschland' as country,
  lat as latitude,
  lng as longitude,
  case isactive when 1 then 'True' else '' end as active,
  id_tblstadium as legacyId
from tblstadium v
where v.id_tblstadium >0 and v.id_tblstadium not in (5,9,10)