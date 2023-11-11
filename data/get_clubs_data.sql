-- get Clubs

select
	name,
	concat(address_one, char(10), address_two) as addressName,
	address_three as street,
    zip_code as zipCode,
	city,
	'Deutschland' as country,
    email,
    founded_date as dateOfFoundation,
	-- description,
    website,
    ishd_id as ishdId,
	case published when 1 then 'True' else '' end as active,
	id as legacyId
from jos_bishl_club

-- get Venues

select
  name,
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