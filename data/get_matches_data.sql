-- get MATCHES data
-- -----------------

-- with history (joining tblteamseason)

select
  json_object('name', cs.py_name, 'alias', cs.py_t_alias) as tournament,
  json_object('name', cast(g.SeasonYear as char(4)), 'alias', cast(g.SeasonYear as char(4))) as season,
  json_object('name', cs.py_round, 'alias', cs.py_round_alias) as round,
    COALESCE(g.Round, 'ALL_GAMES') as matchday_name,
    COALESCE(g.py_md_alias, 'all_games') as matchday_alias,
  json_object(
    'name', COALESCE(g.Round, 'ALL_GAMES'), 
    'alias', COALESCE(g.py_md_alias, 'all_games')
  ) as matchday,
  g.id_tblGame as matchId,
    thc.py_alias as H_clubAlias,
    thc.py_alias as H_teamAlias,
    th.NameAffix as H_teamName,
    tsh.name as H_teamFullName,
    tsh.shortname as H_teamShortname,
    tsh.tinyName as H_teamTinyName,
    tsh.py_logo as H_teamLogo,
    st.GoalsH as H_goalsFor,
    st.GoalsA as H_goalsAgainst,
  json_object(
    'clubAlias', thc.py_alias,
    'teamAlias', th.py_alias,
    -- 'teamId', th.py_team_id,
    'name', th.NameAffix,
    'fullName', tsh.Name, 
    'shortName', tsh.ShortName,
    'tinyName', tsh.TinyName,
    'logo', tsh.py_logo,
    'stats', json_object(
      'goalsFor', st.GoalsH,
      'goalsAgainst', st.GoalsA
    )
  ) as home,
  -- ta.Name, ta.ShortName, ta.tinyName,
    tac.py_alias as A_clubAlias,
    ta.py_alias as A_teamAlias,
    ta.NameAffix as A_teamName,
    tsa.name as A_teamFullName,
    tsa.shortname as A_teamShortname,
    tsa.tinyName as A_teamTinyName,
    tsa.py_logo as A_teamLogo,
    st.GoalsA as A_goalsFor,
    st.GoalsH as A_goalsAgainst,  
  json_object(
    'clubAlias', tac.py_alias,
    'teamAlias', ta.py_alias,
    -- 'teamId', ta.py_team_id,
    'name', ta.NameAffix,
    'fullName', tsa.Name, 
    'shortName', tsa.ShortName,
    'tinyName', tsa.TinyName,
    'logo', tsa.py_logo,
    'stats', json_object(
      'goalsFor', st.GoalsA,
      'goalsAgainst', st.GoalsH
    )
  ) as away,
  gs.py_doc as matchStatus,
  s.Name as venue,
  json_object(
    'venueId', coalesce(s.py_id, ''),
    'name', coalesce(s.Name, 'unbekannter Ort'),
    'alias', coalesce(s.py_alias, 'unbekannter-ort')
  ) as venue,
  case g.IsOvertime when 1 then 'True' else 'False' end as overtime,
  case g.IsShootout when 1 then 'True' else 'False' end as shootout,
  json_object(
    'key', 
    case when g.IsOvertime = 1 then 'OVERTIME' else 
      case when g.IsShootout = 1 then 'SHOOTOUT' else 'REGULAR' end    
    end,
    'value',
    case when g.IsOvertime = 1 then 'Verlängerung' else
      case when g.IsShootout = 1 then 'Penaltyschießen' else 'Regulär' end
    end
  ) as finishType,
  g.startdate as startDate,
  -- DATE_ADD(g.startdate, INTERVAL 7 MONTH) as startDate,
  'True' as published,
  case when g.id_fk_referee1 > 0 then
    json_object(
      'userId', concat('SYS_LEGACY_ID_', r1.id_tblOfficial),
      'firstName', r1.firstName,
      'lastName', r1.lastName,
      'clubId', concat('SYS_LEGACY_ID_', r1.id_fk_Club),
      'clubName', r1c.name
    ) 
  else '' end as referee1,
  case when g.id_fk_referee2 > 0 then
    json_object(
      'userId', concat( 'SYS_LEGACY_ID_', r2.id_tblOfficial),
      'firstName', r2.firstName,
      'lastName', r2.lastName,
      'clubId', concat( 'SYS_LEGACY_ID_', r2.id_fk_Club),
      'clubName', r2c.name
    ) 
  else '' end as referee2
from tblgame as g
join tblchampionship as cs on g.id_fk_Championship=cs.id_tblChampionship
join tblgamestatus as gs on g.id_fk_GameStatus=gs.id_tblGameStatus
join tblstadium as s on g.id_fk_Stadium=s.id_tblStadium
join tblteamseason as tsh on g.id_fk_TeamHome=tsh.id_fk_Team and g.SeasonYear=tsh.SeasonYear
join tblteam as th on tsh.id_fk_Team=th.id_tblTeam
join tblclub as thc on th.id_fk_Club=thc.id_tblClub
join tblteamseason as tsa on g.id_fk_TeamAway=tsa.id_fk_Team and g.SeasonYear=tsa.SeasonYear
join tblteam as ta on tsa.id_fk_Team=ta.id_tblTeam
join tblclub as tac on ta.id_fk_Club=tac.id_tblClub
left join tblgamestats as st on g.id_tblgame = st.id_fk_game
left join tblofficial as r1 on g.id_fk_Referee1=r1.id_tblOfficial
left join tblclub as r1c on r1.id_fk_Club=r1c.id_tblClub
left join tblofficial as r2 on g.id_fk_Referee2=r2.id_tblOfficial
left join tblclub as r2c on r2.id_fk_Club=r2c.id_tblClub
where g.SeasonYear not in (2020,2021)
  -- and g.SeasonYear <= 2023
  and cs.id_tblchampionship not in (46,34,2,32,8,13,33,4,5)
  and g.SeasonYear = 2024
  -- and cs.id_tblchampionship = 27
and g.id_fk_gamestatus in (2,4)
  and cs.isextern=0
order by cs.py_t_alias, g.SeasonYear, g.Round, g.MatchDay, g.StartDate


-- 2024 dummy for tests
  select
    json_object('name', cs.py_name, 'alias', cs.py_t_alias) as tournament,
    json_object('name', cast(g.SeasonYear as char(4)), 'alias', cast(g.SeasonYear as char(4))) as season,
    json_object('name', cs.py_round, 'alias', cs.py_round_alias) as round,
      COALESCE(g.Round, 'ALL_GAMES') as matchday_name,
      COALESCE(g.py_md_alias, 'all_games') as matchday_alias,
    json_object(
      'name', COALESCE(g.Round, 'ALL_GAMES'), 
      'alias', COALESCE(g.py_md_alias, 'all_games')
    ) as matchday,
    g.id_tblGame as matchId,
      thc.py_alias as H_clubAlias,
      thc.py_alias as H_teamAlias,
      th.NameAffix as H_teamName,
      tsh.name as H_teamFullName,
      tsh.shortname as H_teamShortname,
      tsh.tinyName as H_teamTinyName,
      tsh.py_logo as H_teamLogo,
      st.GoalsH as H_goalsFor,
      st.GoalsA as H_goalsAgainst,
    json_object(
      'clubAlias', thc.py_alias,
      'teamAlias', th.py_alias,
      -- 'teamId', th.py_team_id,
      'name', th.NameAffix,
      'fullName', tsh.Name, 
      'shortName', tsh.ShortName,
      'tinyName', tsh.TinyName,
      'logo', tsh.py_logo
    ) as home,
    -- ta.Name, ta.ShortName, ta.tinyName,
      tac.py_alias as A_clubAlias,
      ta.py_alias as A_teamAlias,
      ta.NameAffix as A_teamName,
      tsa.name as A_teamFullName,
      tsa.shortname as A_teamShortname,
      tsa.tinyName as A_teamTinyName,
      tsa.py_logo as A_teamLogo,
      st.GoalsA as A_goalsFor,
      st.GoalsH as A_goalsAgainst,  
    json_object(
      'clubAlias', tac.py_alias,
      'teamAlias', ta.py_alias,
      -- 'teamId', ta.py_team_id,
      'name', ta.NameAffix,
      'fullName', tsa.Name, 
      'shortName', tsa.ShortName,
      'tinyName', tsa.TinyName,
      'logo', tsa.py_logo
    ) as away,
    json_object(
      'key', 'SCHEDULED',
      'value', 'angesetzt'
    ) as matchStatus,
    s.Name as venue,
    json_object(
      'venueId', coalesce(s.py_id, ''),
      'name', coalesce(s.Name, 'unbekannter Ort'),
      'alias', coalesce(s.py_alias, 'unbekannter-ort')
    ) as venue,
    json_object(
      'key', 'REGULAR',
      'value', 'Regulär' 
    ) as finishType,
    -- g.startdate as startDate,
    DATE_ADD(g.startdate, INTERVAL 7 MONTH) as startDate,
    'True' as published
  from tblgame as g
  join tblchampionship as cs on g.id_fk_Championship=cs.id_tblChampionship
  join tblgamestatus as gs on g.id_fk_GameStatus=gs.id_tblGameStatus
  join tblstadium as s on g.id_fk_Stadium=s.id_tblStadium
  join tblteamseason as tsh on g.id_fk_TeamHome=tsh.id_fk_Team and g.SeasonYear=tsh.SeasonYear
  join tblteam as th on tsh.id_fk_Team=th.id_tblTeam
  join tblclub as thc on th.id_fk_Club=thc.id_tblClub
  join tblteamseason as tsa on g.id_fk_TeamAway=tsa.id_fk_Team and g.SeasonYear=tsa.SeasonYear
  join tblteam as ta on tsa.id_fk_Team=ta.id_tblTeam
  join tblclub as tac on ta.id_fk_Club=tac.id_tblClub
  left join tblgamestats as st on g.id_tblgame = st.id_fk_game
  left join tblofficial as r1 on g.id_fk_Referee1=r1.id_tblOfficial
  left join tblclub as r1c on r1.id_fk_Club=r1c.id_tblClub
  left join tblofficial as r2 on g.id_fk_Referee2=r2.id_tblOfficial
  left join tblclub as r2c on r2.id_fk_Club=r2c.id_tblClub
  where g.SeasonYear not in (2020,2021)
    -- and g.SeasonYear <= 2023
    -- and cs.id_tblchampionship not in (46,34,2,32,8,13,33,4,5)
    and g.SeasonYear = 2024
    and cs.id_tblchampionship = 27
  and g.id_fk_gamestatus in (2,4)
    and cs.isextern=0
  order by cs.py_t_alias, g.SeasonYear, g.Round, g.MatchDay, g.StartDate


-- cehck
  select g.SeasonYear, g.id_fk_teamhome, tsh.id_fk_Team
  from tblgame as g
  join tblchampionship as cs on g.id_fk_Championship=cs.id_tblChampionship
  join tblgamestatus as gs on g.id_fk_GameStatus=gs.id_tblGameStatus
  join tblstadium as s on g.id_fk_Stadium=s.id_tblStadium
  left join tblteamseason as tsh on g.id_fk_TeamHome=tsh.id_fk_Team and g.SeasonYear=tsh.SeasonYear
  where g.SeasonYear not in (2020,2021)
    and g.SeasonYear <= 2023
    and g.id_fk_gamestatus in (2,4)
    and cs.id_tblchampionship not in (46,34,2,32,8,13,33,4,5)
    and cs.isextern=0

    and tsh.id_fk_Team is null

  -- corrections
update tblgame set id_fk_teamhome=170 where id_fk_teamhome=137;
update tblgame set id_fk_teamaway=170 where id_fk_teamaway=137;
update tblroster set id_fk_team=170 where id_fk_team=137;
update tblscoreboard set id_fk_team=170 where id_fk_team=137;
update tblpenaltyboard set id_fk_team=170 where id_fk_team=137;
update tblteamplayer set id_fk_team=170 where id_fk_team=137;
update tblteamseason set id_fk_team=170 where id_fk_team=137;
update tblteamchampionship set id_fk_team=170 where id_fk_team=137;



  

-- without history (NOT joining tblteamseason)
-- wurde nicht benutzt
select
  cs.py_code as t_tinyName,
  g.SeasonYear as seasonYear,
  cs.py_round as r_name,
  COALESCE(g.Round, 'ALL_GAMES') as md_name,
  g.id_tblGame as matchId,
  th.Name, th.ShortName, th.tinyName,
  json_object(
    'teamId', th.py_team_id,
    'fullName', th.Name, 
    'shortName', th.ShortName,
    'tinyName', th.TinyName,
    'logo', th.py_logo
  ) as homeTeam,
  ta.Name, ta.ShortName, ta.tinyName,
  json_object(
    'teamId', ta.py_team_id,
    'fullName', ta.Name, 
    'shortName', ta.ShortName,
    'tinyName', ta.TinyName,
    'logo', ta.py_logo
  ) as awayTeam,
  gs.Name as status,
  s.Name as venue,
  st.GoalsH as homeScore,
  st.GoalsA as awayScore,
  g.IsOvertime as overtime,
  g.IsShootout as shootout,
  g.startdate as startTime,
  'True' as published
from tblgame as g
join tblchampionship as cs on g.id_fk_Championship=cs.id_tblChampionship
join tblgamestatus as gs on g.id_fk_GameStatus=gs.id_tblGameStatus
join tblstadium as s on g.id_fk_Stadium=s.id_tblStadium
join tblteam as th on g.id_fk_TeamHome=th.id_tblTeam
join tblteam as ta on g.id_fk_TeamAway=ta.id_tblTeam
left join tblgamestats as st on g.id_tblgame = st.id_fk_game
where g.SeasonYear in (2022,2023)
and cs.id_tblchampionship not in (-1, 46)
and id_fk_gamestatus in (2,4)

  -- data preparation
SELECT * FROM `tblchampionship` where name like '%Playoffs%'
update  `tblchampionship` set py_round='Playoffs' where name like '%Playoffs%'

SELECT * FROM `tblchampionship` where name like '%Meisterrunde%'
update  `tblchampionship` set py_round='Meisterrunde' where name like '%Meisterrunde%'

SELECT * FROM `tblchampionship` where name like '%Platz%'
update  `tblchampionship` set py_round='Platzierungsrunde' where name like '%Platz%'


update `tblchampionship` set py_round = MenuText
update `tblchampionship` set py_round = null where isextern=1

SELECT * FROM `tblchampionship`
where 1=1
and not (
    py_round in ('Playoffs', 'Meisterrunde', 'Platzierungsrunde', 'Qualifikationsrunde', 'Hauptrunde')
  or 
    py_round like 'Gruppe%' or py_round like 'Staffel%'
    )
-- and py_round NOT in ('Playoffs', 'Meisterrunde', 'Platzierungsrunde', 'Qualifikationsrunde')  
and IsExtern=0
ORDER BY `tblchampionship`.`py_round` ASC

update `tblchampionship`
set py_round = 'Hauptrunde'
where 1=1
and not (
    py_round in ('Playoffs', 'Meisterrunde', 'Platzierungsrunde', 'Qualifikationsrunde', 'Hauptrunde')
  or 
    py_round like 'Gruppe%' or py_round like 'Staffel%'
    )
-- and py_round NOT in ('Playoffs', 'Meisterrunde', 'Platzierungsrunde', 'Qualifikationsrunde')  
and IsExtern=0


db.tournaments.updateOne({tiny_name:"RLO"}, {$push: {"seasons.$[seasons].rounds": {name:"HAUPT"}}}, { arrayFilters: [{"seasons.year": 2022}]})


db.tournaments.updateOne({tiny_name:"RLO"}, {$set: {"seasons.$[y].test": "test4"}}, {arrayFilters: [ {"y.year": 2023} ]} )
db.tournaments.updateOne({tiny_name:"RLO"}, {$set: {"seasons.$[y].rounds.$[r].test": "test4"}}, {arrayFilters: [ {"y.year": 2023}, {"r.name": "Hauptrunde"} ]} )



-- versuch, roster mit zu joinen
select
  json_object('name', cs.py_name, 'alias', cs.py_t_alias) as tournament,
  json_object('name', cast(g.SeasonYear as char(4)), 'alias', cast(g.SeasonYear as char(4))) as season,
  json_object('name', cs.py_round, 'alias', cs.py_round_alias) as round,
  json_object(
    'name', COALESCE(g.Round, 'ALL_GAMES'), 
    'alias', COALESCE(g.py_md_alias, 'all_games')
  ) as matchday,
  g.id_tblGame as matchId,
  json_object(
    'clubAlias', thc.py_alias,
    'teamAlias', th.py_alias,
    -- 'teamId', th.py_team_id,
    'name', th.NameAffix,
    'fullName', tsh.Name, 
    'shortName', tsh.ShortName,
    'tinyName', tsh.TinyName,
    'logo', tsh.py_logo,
    'stats', json_object(
      'goalsFor', st.GoalsH,
      'goalsAgainst', st.GoalsA
    ),
    'roster', 
      cast(
          concat(
              '[', 
              GROUP_CONCAT(
                  json_object(
                      'player', json_object(
                          'firstName', ph.FirstName,
                          'lastName', ph.LastName,
                          'jerseyNumber', rh.JerseyNo
                      )
                  )
              ),
              ']'
        )
          as JSON
      )                 
  ) as home,
  ta.Name, ta.ShortName, ta.tinyName,
  json_object(
    'clubAlias', tac.py_alias,
    'teamAlias', ta.py_alias,
    -- 'teamId', ta.py_team_id,
    'name', ta.NameAffix,
    'fullName', tsa.Name, 
    'shortName', tsa.ShortName,
    'tinyName', tsa.TinyName,
    'logo', tsa.py_logo,
    'stats', json_object(
      'goalsFor', st.GoalsA,
      'goalsAgainst', st.GoalsH
    )
  ) as away,
  gs.py_doc as matchStatus,
  s.Name as venue,
  case g.IsOvertime when 1 then 'True' else 'False' end as overtime,
  case g.IsShootout when 1 then 'True' else 'False' end as shootout,
  json_object(
    'key', 
    case when g.IsOvertime = 1 then 'OVERTIME' else 
      case when g.IsShootout = 1 then 'SHOOTOUT' else 'REGULAR' end    
    end,
    'value',
    case when g.IsOvertime = 1 then 'Verlängerung' else
      case when g.IsShootout = 1 then 'Penaltyschießen' else 'Regulär' end
    end
  ) as finishType,
  g.startdate as startDate,
  'True' as published,
  case when g.id_fk_referee1 > 0 then
    json_object(
      'user_id', concat('SYS_LEGACY_ID_', r1.id_tblOfficial),
      'firstName', r1.firstName,
      'lastName', r1.lastName,
      'club_id', concat('SYS_LEGACY_ID_', r1.id_fk_Club),
      'club_name', r1c.name
    ) 
  else '' end as referee1,
  case when g.id_fk_referee2 > 0 then
    json_object(
      'user_id', concat( 'SYS_LEGACY_ID_', r2.id_tblOfficial),
      'firstName', r2.firstName,
      'lastName', r2.lastName,
      'club_id', concat( 'SYS_LEGACY_ID_', r2.id_fk_Club),
      'club_name', r2c.name
    ) 
  else '' end as referee2
from tblgame as g
join tblchampionship as cs on g.id_fk_Championship=cs.id_tblChampionship
join tblgamestatus as gs on g.id_fk_GameStatus=gs.id_tblGameStatus
join tblstadium as s on g.id_fk_Stadium=s.id_tblStadium
join tblteamseason as tsh on g.id_fk_TeamHome=tsh.id_fk_Team and g.SeasonYear=tsh.SeasonYear
join tblteam as th on tsh.id_fk_Team=th.id_tblTeam
join tblclub as thc on th.id_fk_Club=thc.id_tblClub
join tblteamseason as tsa on g.id_fk_TeamAway=tsa.id_fk_Team and g.SeasonYear=tsa.SeasonYear
join tblteam as ta on tsa.id_fk_Team=ta.id_tblTeam
join tblclub as tac on ta.id_fk_Club=tac.id_tblClub
join tblroster as rh on g.id_tblGame = rh.id_fk_Game and g.id_fk_TeamHome=rh.id_fk_Team
join tblplayer as ph on rh.id_fk_Player = ph.id_tblPlayer
left join tblgamestats as st on g.id_tblgame = st.id_fk_game
left join tblofficial as r1 on g.id_fk_Referee1=r1.id_tblOfficial
left join tblclub as r1c on r1.id_fk_Club=r1c.id_tblClub
left join tblofficial as r2 on g.id_fk_Referee2=r2.id_tblOfficial
left join tblclub as r2c on r2.id_fk_Club=r2c.id_tblClub
where g.SeasonYear in (2022,2023)
and cs.id_tblchampionship not in (-1, 46)
and id_fk_gamestatus in (2,4)
and id_tblGame = 7445


-- nur der roster

  
select g.id_tblGame,
cast(
    CONCAT(
        '[',
      GROUP_CONCAT(
            json_object(
                'firstName', ph.FirstName,
                'lastName', ph.LastName
            )
        ),
        ']'
    ) as JSON
) as roster
FROM tblgame as g
JOIN tblroster as rh 
  on g.id_tblGame = rh.id_fk_Game
  and g.id_fk_TeamHome=rh.id_fk_Team
JOIN tblplayer as ph
  on rh.id_fk_Player = ph.id_tblPlayer
WHERE id_tblGame = 7445
GROUP BY g.id_tblGame


-- roster flat
-- --------------
select *
from (
  select 
    g.id_tblGame as match_id,
    'home' as team_flag,
    json_object(
      'playerId', coalesce(ph.py_id, 'n/a'),
      'firstName', ph.display_firstName,
      'lastName', ph.display_lastName,
      'jerseyNumber', rh.JerseyNo
    ) as player,
    json_object(
      'key', case 
      when rh.IsGoalie = 1 then 'G' 
        when rh.IsCaptain = 1 then 'C'
        when rh.IsAssistant = 1 then 'A'
        else 'F' 
      end,
      'value', case
      when rh.IsGoalie = 1 then 'Goalie'
        when rh.IsCaptain = 1 then 'Captain'
        when rh.IsAssistant = 1 then 'Assistant'
        else 'Feldspieler'
      end
    ) as playerPosition,
    tph.PassNo as passNumber
  FROM tblgame as g
  JOIN tblchampionship cs on g.id_fk_Championship=cs.id_tblChampionship
  JOIN tblroster as rh 
    on g.id_tblGame = rh.id_fk_Game
    and g.id_fk_TeamHome=rh.id_fk_Team
  JOIN tblplayer as ph
    on rh.id_fk_Player = ph.id_tblPlayer
  JOIN tblteamplayer as tph
    ON ph.id_tblPlayer = tph.id_fk_Player and g.id_fk_TeamHome=tph.id_fk_Team and g.SeasonYear=tph.SeasonYear
  WHERE 1=1
    -- and id_tblGame = 7445
    and g.SeasonYear not in (2020,2021)
    and g.SeasonYear = 2019
    and g.id_fk_Championship not in (46,34,2,32,8,13,33,4,5)
    and g.id_fk_gamestatus in (2,4)
    and cs.isExtern=0

  union all

  select
    g.id_tblGame as match_id,
    'away' as team_flag,
    json_object(
      'playerId', coalesce(pa.py_id, 'n/a'),
      'firstName', pa.display_firstName,
      'lastName', pa.display_lastName,
      'jerseyNumber', ra.JerseyNo
    ) as player,
    json_object(
      'key', case 
      when ra.IsGoalie = 1 then 'G' 
        when ra.IsCaptain = 1 then 'C'
        when ra.IsAssistant = 1 then 'A'
        else 'F' 
      end,
      'value', case
      when ra.IsGoalie = 1 then 'Goalie'
        when ra.IsCaptain = 1 then 'Captain'
        when ra.IsAssistant = 1 then 'Assistant'
        else 'Feldspieler'
      end
    ) as playerPosition,
    tpa.PassNo as passNumber
  FROM tblgame as g
  JOIN tblchampionship cs on g.id_fk_Championship=cs.id_tblChampionship
  JOIN tblroster as ra
    ON g.id_tblGame = ra.id_fk_Game
    and g.id_fk_TeamAway=ra.id_fk_Team
  join tblplayer as pa
    on ra.id_fk_Player = pa.id_tblPlayer
  join tblteamplayer as tpa
    ON pa.id_tblPlayer = tpa.id_fk_Player and g.id_fk_TeamAway=tpa.id_fk_Team and g.SeasonYear=tpa.SeasonYear
  WHERE 1=1
    -- and id_tblGame = 7445
    and g.SeasonYear not in (2020,2021)
    and g.SeasonYear = 2019
    and g.id_fk_Championship not in (46,34,2,32,8,13,33,4,5)
    and g.id_fk_gamestatus in (2,4)
    and cs.isExtern=0
) t
order by 1,2


-- update tblteamplayer (hochmelden)
  select 
    distinct
      concat('insert into tblteamplayer (id_fk_Team,SeasonYear,id_fk_Player,PassNo,JerseyNo,IsVisible,IsMajorTeam,IsCalled,`Status`,Remarks) values (', team_id ,', 2023, ', player_id, ', ''', st.passNo,''' , ', st.JerseyNo, ', 1, 0, 1, ''spielberechtig'', '''');') as upd_sql
  from (
    select 
      g.id_tblGame as match_id,
      'home' as team_flag,
      g.id_fk_TeamHome as team_id,
      ph.id_tblPlayer as player_id,
      ph.FirstName,
      ph.LastName,
      tph.PassNo as passNumber,
      tph.JerseyNo
    FROM tblgame as g
    JOIN tblroster as rh 
      on g.id_tblGame = rh.id_fk_Game
      and g.id_fk_TeamHome=rh.id_fk_Team
    JOIN tblplayer as ph
      on rh.id_fk_Player = ph.id_tblPlayer
    LEFT JOIN tblteamplayer as tph
      ON ph.id_tblPlayer = tph.id_fk_Player and g.id_fk_TeamHome=tph.id_fk_Team and g.SeasonYear=tph.SeasonYear
    WHERE 1=1
      and g.seasonyear=2023
      and g.id_fk_championship in (27,49,29)


    union all

    select
      g.id_tblGame as match_id,
      'away' as team_flag,
      g.id_fk_TeamAway as team_id,
      pa.id_tblPlayer as player_id,
      pa.FirstName,
      pa.LastName,
      tpa.PassNo as passNumber,
      tpa.JerseyNo
    FROM tblgame as g
    JOIN tblroster as ra
      ON g.id_tblGame = ra.id_fk_Game
      and g.id_fk_TeamAway=ra.id_fk_Team
    join tblplayer as pa
      on ra.id_fk_Player = pa.id_tblPlayer
    left join tblteamplayer as tpa
      ON pa.id_tblPlayer = tpa.id_fk_Player and g.id_fk_TeamAway=tpa.id_fk_Team and g.SeasonYear=tpa.SeasonYear
    WHERE 1=1
      and g.seasonyear=2023
      and g.id_fk_championship in (27,49,29)
  ) t
    join tblteamplayer as st
    on t.player_id = st.id_fk_player and st.seasonyear=2023 
  where 1=1
  -- and t.match_id = 7435
  and passNumber is null
  order by 1

-- chcek
  select 
  t.match_id,
  t.team_flag,
  t.py_id,
  t.FirstName,
  t.LastName,
  count(*)
  from (
    select 
      g.id_tblGame as match_id,
      'home' as team_flag,
      ph.py_id,
      ph.FirstName,
      ph.LastName
    FROM tblgame as g
      join tblchampionship cs on g.id_fk_Championship=cs.id_tblChampionship

    JOIN tblroster as rh 
      on g.id_tblGame = rh.id_fk_Game
      and g.id_fk_TeamHome=rh.id_fk_Team
    JOIN tblplayer as ph
      on rh.id_fk_Player = ph.id_tblPlayer
    JOIN tblteamplayer as tph
      ON ph.id_tblPlayer = tph.id_fk_Player and g.id_fk_TeamHome=tph.id_fk_Team and g.SeasonYear=tph.SeasonYear
    WHERE 1=1
      -- and id_tblGame = 7445
      and g.SeasonYear not in (2020,2021)
      and g.SeasonYear = 2019
      and g.id_fk_Championship not in (46,34,2,32,8,13,33,4,5)
      and g.id_fk_gamestatus in (2,4)
      and cs.isExtern=0
    union all

    select
      g.id_tblGame as match_id,
      'away' as team_flag,
      pa.py_id,
      pa.FirstName,
      pa.LastName
    FROM tblgame as g
      join tblchampionship cs on g.id_fk_Championship=cs.id_tblChampionship

    JOIN tblroster as ra
      ON g.id_tblGame = ra.id_fk_Game
      and g.id_fk_TeamAway=ra.id_fk_Team
    join tblplayer as pa
      on ra.id_fk_Player = pa.id_tblPlayer
    join tblteamplayer as tpa
      ON pa.id_tblPlayer = tpa.id_fk_Player and g.id_fk_TeamAway=tpa.id_fk_Team and g.SeasonYear=tpa.SeasonYear
    WHERE 1=1
      -- and id_tblGame = 7445
      and g.SeasonYear not in (2020,2021)
      and g.SeasonYear = 2019
      and g.id_fk_Championship not in (46,34,2,32,8,13,33,4,5)
      and g.id_fk_gamestatus in (2,4)
      and cs.isExtern=0
  ) t
  group by t.match_id,
  t.team_flag,
  t.py_id,
  t.FirstName,
  t.Lastname
  having count(*) >1
  order by 1,2

-- ergebnis; # legacy_id 1209
"match_id","team_flag","py_id","FirstName","LastName","count(*)"
"7279","home","66f1783e633f27247d96418c","Nils","Herrle","2"
"7284","home","66f1783e633f27247d96418c","Nils","Herrle","2"
"7287","away","66f1783e633f27247d96418c","Nils","Herrle","2"
"7296","home","66f1783e633f27247d96418c","Nils","Herrle","2"
"7298","away","66f1783e633f27247d96418c","Nils","Herrle","2"
"7314","away","66f1783e633f27247d96418c","Nils","Herrle","2"
"7319","home","66f1783e633f27247d96418c","Nils","Herrle","2"
"7439","home","66f1783e633f27247d96418c","Nils","Herrle","2"
"7440","away","66f1783e633f27247d96418c","Nils","Herrle","2"
"7445","away","66f1783e633f27247d96418c","Nils","Herrle","2"


-- check 2 - fehlende Spieler (roster.id_fk_player = 0)
select 
t.match_id,
t.team_flag,
t.id_fk_player,
t.py_id,
t.FirstName,
t.LastName
from (
  select 
    g.id_tblGame as match_id,
    'home' as team_flag,
    rh.id_fk_Player,
    ph.py_id,
    ph.FirstName,
    ph.LastName
  FROM tblgame as g
  JOIN tblroster as rh 
    on g.id_tblGame = rh.id_fk_Game
    and g.id_fk_TeamHome=rh.id_fk_Team
  left JOIN tblplayer as ph
    on rh.id_fk_Player = ph.id_tblPlayer
  left JOIN tblteamplayer as tph
    ON ph.id_tblPlayer = tph.id_fk_Player and g.id_fk_TeamHome=tph.id_fk_Team and g.SeasonYear=tph.SeasonYear
  WHERE 1=1
    -- and id_tblGame = 7445
    and g.seasonyear=2023
    and g.id_fk_championship in (27,49,29)


  union all

  select
    g.id_tblGame as match_id,
    'away' as team_flag,
    ra.id_fk_Player,
    pa.py_id,
    pa.FirstName,
    pa.LastName
  FROM tblgame as g
  JOIN tblroster as ra
    ON g.id_tblGame = ra.id_fk_Game
    and g.id_fk_TeamAway=ra.id_fk_Team
  left join tblplayer as pa
    on ra.id_fk_Player = pa.id_tblPlayer
  left join tblteamplayer as tpa
    ON pa.id_tblPlayer = tpa.id_fk_Player and g.id_fk_TeamAway=tpa.id_fk_Team and g.SeasonYear=tpa.SeasonYear
  WHERE 1=1
    -- and id_tblGame = 7445
    and g.seasonyear=2023
    and g.id_fk_championship in (27,49,29)
) t
where t.py_id is null
order by 1,2

-- fix missing players
insert into tblteamplayer (id_fk_Team, SeasonYear, id_fk_Player, PassNo,JerseyNo) values (8,2023,1007,'8447',0);
insert into tblteamplayer (id_fk_Team, SeasonYear, id_fk_Player, PassNo,JerseyNo) values (48,2023,2456,'0035',0);



----- GET SCORES DATA

select 
  g.id_tblGame as match_id,
  case when sb.id_fk_Team=g.id_fk_TeamHome then 'home' else 'away' end as team_flag,
  left(cast(GameTime as char), 5) as matchTime,
  json_object(
    'playerId', pg.py_id,
    'firstName', pg.display_firstName,
    'lastName', pg.display_lastName,
    'jerseyNumber', rg.JerseyNo
  ) as goalPlayer,
  case when pa.py_id is null then null else
      json_object(
        'playerId', pa.py_id,
        'firstName', pa.display_firstName,
        'lastName', pa.display_lastName,
        'jerseyNumber', ra.JerseyNo
      ) 
  end as assistPlayer
FROM tblscoreboard sb
JOIN tblgame as g
  on sb.id_fk_Game = g.id_tblGame
JOIN tblchampionship cs
  on g.id_fk_Championship=cs.id_tblChampionship
JOIN tblroster as rg
  on sb.id_fk_Game=rg.id_fk_Game and sb.id_fk_Team=rg.id_fk_Team and sb.id_fk_GoalBy=rg.id_fk_Player
JOIN tblplayer as pg
  on rg.id_fk_Player=pg.id_tblPlayer
LEFT JOIN tblroster as ra
  on sb.id_fk_Game=ra.id_fk_Game and sb.id_fk_Team=ra.id_fk_Team and sb.id_fk_AssistBy=ra.id_fk_Player
LEFT JOIN tblplayer as pa
  on ra.id_fk_Player=pa.id_tblPlayer
WHERE 1=1
  -- and id_tblGame = 7445
  and g.SeasonYear not in (2020,2021)
  and g.SeasonYear <= 2019
  and g.id_fk_Championship not in (46,34,2,32,8,13,33,4,5)
  and g.id_fk_gamestatus in (2,4)
  and cs.isExtern=0
ORDER BY 1, 2 desc
  

----- GET PENALTIES DATA
select 
  g.id_tblGame as match_id,
  case when pb.id_fk_Team=g.id_fk_TeamHome then 'home' else 'away' end as team_flag,
  left(cast(GameTimeStart as char), 5) as matchTimeStart,
  left(cast(GameTimeEnd as char), 5) as matchTimeEnd,
  json_object(
    'playerId', pp.py_id,
    'firstName', pp.display_firstName,
    'lastName', pp.display_lastName,
    'jerseyNumber', rp.JerseyNo
  ) as penaltyPlayer,
  json_object(
    'key', pc.Code,
    'value', pc.Description
  ) as penaltyCode,
  pb.Minutes as penaltyMinutes,
  case when pb.isGM=1 then 'True' else 'False' end as isGM,
  case when pb.isMP=1 then 'True' else 'False' end as isMP
FROM tblpenaltyboard pb
JOIN tblgame as g
  on pb.id_fk_Game = g.id_tblGame
JOIN tblchampionship cs
  on g.id_fk_Championship=cs.id_tblChampionship
JOIN tblroster as rp
  on pb.id_fk_Game=rp.id_fk_Game and pb.id_fk_Team=rp.id_fk_Team and pb.id_fk_Player=rp.id_fk_Player
JOIN tblplayer as pp
  on rp.id_fk_Player=pp.id_tblPlayer
JOIN tblpenaltycode as pc
  on pb.id_fk_PenaltyCode=pc.id_tblPenaltyCode and g.SeasonYear=pc.SeasonYear
WHERE 1=1
  -- and id_tblGame = 7445
  and g.SeasonYear not in (2020,2021)
  and g.SeasonYear <= 2019
  and g.id_fk_Championship not in (46,34,2,32,8,13,33,4,5)
  and g.id_fk_gamestatus in (2,4)
  and cs.isExtern=0



-- fix tblteamseason
-- check
SELECT ts.name, t.name as t_name, ts.shortname, t.ShortName as t_shortname, ts.tinyname,t.tinyName as t_tinyname, ts.py_logo, ts.py_team_id,
t.py_team_id, t.py_logo, t.py_alias FROM `tblteamseason` ts
join tblteam t on ts.id_fk_team=t.id_tblTeam
where ts.SeasonYear=2024

UPDATE tblteamseason ts
inner join tblteam t ON ts.id_fk_team=t.id_tblTeam
SET ts.tinyName=t.tinyName, ts.py_team_id=t.py_team_id, ts.py_logo=t.py_logo
WHERE ts.seasonYear=2024;