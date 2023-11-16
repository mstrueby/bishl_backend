-- get Clubs
select
    c.name,
    replace(
    replace(
      replace(
        replace(  
          replace(
            replace(
              replace(lower(trim(c.name)), ' ', '-')
              , 'ü', 'ue')
            , 'ö', 'oe')
          , 'ä' ,'ae')
        , 'ß', 'ss')
      , '`', '-')
    , '.', '') as alias,
    concat(c.AddressLine1, ', ' , c.AddressLine2) as addressName,
    c.AddressLine3 as street,
    c.PostalCode as zipCode,
    c.City,
    'Deutschland' as country,
    c.EMail as email,
    year(c.DateFounded) as yearOfFoundation,    
    c.WebPage as website,
    c.ISHDID as ishdId,
    case c.IsActive when 1 then 'True' else '' end as published,
    c.id_tblClub as legacyId
from tblclub c
where c.id_tblClub>0