-- get Clubs
select
  trim(c.name) as name,
  c.py_alias as alias,
  concat(c.AddressLine1, ', ' , c.AddressLine2) as addressName,
  c.AddressLine3 as street,
  c.PostalCode as zipCode,
  c.City,
  'Deutschland' as country,
  c.EMail as email,
  year(c.DateFounded) as yearOfFoundation,    
  c.WebPage as website,
  c.ISHDID as ishdId,
  case c.IsActive when 1 then 'True' else '' end as active,
  c.id_tblClub as legacyId,
  c.py_logo as logo,
  '' as teams
from tblclub c
where c.id_tblClub>0


-- sub doc TEAMS
SELECT 
  c.py_alias as clubAlias,
  concat(t.teamNumber, '. ', ag.Name) as name,
  -- t.py_alias as teamAlias,
  t.py_alias as alias,
  t.name as fullName,
  t.shortName as shortName, 
  t.tinyName as tinyName, 
  -- t.NameAffix as nameAffix,
  ag.Name as ageGroup,
  t.teamNumber as teamNumber,
  t.Phone as phoneNumber, 
  t.EMail as email, 
  t.WebPage as website,
  case t.IsActive when 1 then 'True' else '' end as active,
  case t.IsExtern when 1 then 'True' else '' end as external,
  t.ISHDID as ishdId,
  t.id_tblTeam as legacyId
FROM tblteam as t
left JOIN tblagegroup as ag on t.id_fk_AgeGroup=ag.id_tblAgeGroup
left JOIN tblclub as c on t.id_fk_Club=c.id_tblClub
where t.id_tblTeam>0 and c.id_tblClub>0 
and t.isactive=1 
and c.isactive=1

-- Korrekturen
update tblclub
  set py_alias=replace(
  replace(
    replace(
      replace(  
        replace(
          replace(
            replace(lower(trim(name)), ' ', '-')
            , 'ü', 'ue')
          , 'ö', 'oe')
        , 'ä' ,'ae')
      , 'ß', 'ss')
    , '`', '-')
  , '.', '')

update tblteam
  set py_alias=replace(
    replace(
      replace(
        replace(  
          replace(
            replace(
              replace(lower(trim( ISHDID )), ' ', '-')
              , 'ü', 'ue')
            , 'ö', 'oe')
          , 'ä' ,'ae')
        , 'ß', 'ss')
      , '`', '-')
    , '.', '')
  
update tblteam t
inner join tblclub c on t.id_fk_Club=c.id_tblClub
set t.shortName = case 
  when t.teamNumber=1 then c.teamShortName
  else concat(c.teamShortName, ' ', t.teamNumberRoman) 
end;

update tblteam t
inner join tblclub c on t.id_fk_Club=c.id_tblClub
set t.tinyName = case 
  when t.teamNumber=1 then c.teamTinyName
  else concat(c.teamTinyName, t.teamNumber) 
end;

update tblteam t
inner join tblclub c on t.id_fk_Club=c.id_tblClub
set t.py_logo = c.py_logo;