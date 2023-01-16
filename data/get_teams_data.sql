-- get Teams

select
	t.name,
	short_name as shortName,
	tiny_name as tinyName,
    team_num as teamNumber,
    coalesce(ag.name, '') as ageGroup,
    coalesce(c.name, '') as clubName,
    t.contact_name, t.phone_num, t.email, 
	t.description,
    case t.extern_flag when 1 then 'True' else '' end as extern,
    t.ishd_id as ishdId,
	case t.published when 1 then 'True' else '' end as active,
	t.id as legacyId
from jos_bishl_team t
left join jos_bishl_age_group ag on t.agegroup=ag.id
left join jos_bishl_club c on t.club=c.id