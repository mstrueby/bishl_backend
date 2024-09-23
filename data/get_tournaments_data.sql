-- get TOURNAMENT data
-- -----------------------
select 
  cs.name as name,
  py_t_alias as alias,
  cs.Code as tinyName,
  -- json_object("key", ag.py_key, "value", ag.py_value) as ageGroup,
  py_ageGroup as ageGroup,
  'True' as published,
  'True' as active,
  -- '' as external,
  /*
  json_object(
    'numOfPeriods', cs.NumOfPeriods,
    'periodLengthMin', cs.PeriodLength,
    'pointsWinReg', cs.PointsWinReg,
    'pointsLossReg', cs.PointsLossReg,
    'pointsDrawReg', cs.PointsTie,
    'overtime', case when cs.IsOvertime = 1 then 'True' else 'False' end,
    'numOfPeriodsOvertime', cs.NumOfPeriodsOT,
    'periodLengthMinOvertime', cs.PeriodLengthOT,
    'pointsWinOvertime', cs.PointsWinOT,
    'pointsLossOvertime', cs.PointsLossOT,
    'shootout', case when cs.IsShootout = 1 then 'True' else 'False' end,
    'pointsWinShootout', cs.PointsWinSO,
    'pointsLossShootout', cs.PointsLossSO
  ) as defaultSettings,
  */
  json_object(
    'pointsWinReg', cs.PointsWinReg,
    'pointsLossReg', cs.PointsLossReg,
    'pointsDrawReg', cs.PointsTie,
    'pointsWinOvertime', cs.PointsWinOT,
    'pointsLossOvertime', cs.PointsLossOT,
    'pointsWinShootout', cs.PointsWinSO,
    'pointsLossShootout', cs.PointsLossSO
  ) as standingsSettings,
  -- '' as seasons,
  id_tblChampionship as legacyId
from tblchampionship cs
join tblagegroup ag on cs.id_fk_AgeGroup=ag.id_tblAgeGroup
where 1=1
  -- and cs.IsActive=1 
  and py_doc='tournament'
  and cs.id_tblChampionship in (45,14,10,51,35,26,28,27)


-- fixes
  update tblchampionship 
  set py_t_alias=
    replace(
      replace(
        replace(
          replace(  
            replace(
              replace(
                replace(lower(trim(Name)), ' ', '-')
                , 'ü', 'ue')
            , 'ö', 'oe')
          , 'ä' ,'ae')
        , 'ß', 'ss')
      , '`', '-')
    , '.', '')
  where py_doc='tournament'

-- Tests:
  
[{""year"":""2023"", ""published"":""True""}]
[{"year":"2023", "published":"True"}]

db.tournaments.updateOne({tiny_name:"SL"}, { $set: { seasons: [{year: 2023, published: true }] }  })
  
db.tournaments.updateOne({tiny_name:"SL"}, { $push: { seasons: {year: 2023, published: true } }  })
db.tournaments.updateOne({tiny_name:"SL"}, { $push: { seasons: {year: 2022, published: true } }  })
  
db.tournaments.updateMany({}, { $set: { seasons: [{year: 2023, published: true }] }  })



-- get SEASONS data
-- -----------------------
  select distinct
    tcs.SeasonYear as name,
    replace(
      replace(
        replace(
          replace(  
            replace(
              replace(
                replace(lower(trim(tcs.SeasonYear)), ' ', '-')
              , 'ü', 'ue')
            , 'ö', 'oe')
          , 'ä' ,'ae')
        , 'ß', 'ss')
      , '`', '-')
    , '.', '') as alias,
    cs.py_t_alias as t_alias
  from tblteamchampionship tcs
  join tblchampionship cs on tcs.id_fk_Championship=cs.id_tblChampionship
  where 1=1
  and tcs.SeasonYear in (2022, 2023)
  and cs.IsExtern=0
  and cs.id_fk_AgeGroup>0

db.tournaments.updateOne( {tiny_name: "SL"}, { $push: { seasons: {year:2023, published:true} } } )
db.tournaments.updateOne( {tiny_name: "BAM"}, { $push: { seasons: {year:2022, published:true} } } )
db.tournaments.updateOne( {tiny_name: "BAM"}, { $push: { seasons: {year:2023, published:true} } } )
db.tournaments.updateOne( {tiny_name: "JNL"}, { $push: { seasons: {year:2023, published:true} } } )
db.tournaments.updateOne( {tiny_name: "RLO"}, { $push: { seasons: {year:2023, published:true} } } )
db.tournaments.updateOne( {tiny_name: "LL"}, { $push: { seasons: {year:2023, published:true} } } )
db.tournaments.updateOne( {tiny_name: "RLO"}, { $push: { seasons: {year:2022, published:true} } } )
db.tournaments.updateOne( {tiny_name: "LL"}, { $push: { seasons: {year:2022, published:true} } } )
db.tournaments.updateOne( {tiny_name: "JGL"}, { $push: { seasons: {year:2022, published:true} } } )
db.tournaments.updateOne( {tiny_name: "JGL"}, { $push: { seasons: {year:2023, published:true} } } )
db.tournaments.updateOne( {tiny_name: "MINI"}, { $push: { seasons: {year:2022, published:true} } } )
db.tournaments.updateOne( {tiny_name: "MINI"}, { $push: { seasons: {year:2023, published:true} } } )


-- get ROUNDS data
-- -----------------------
  select distinct
      cs.py_t_alias as t_alias,
      tcs.SeasonYear as s_alias,
      cs.py_round as name,
      cs.py_round_alias as alias,
      cs.py_r_create_table as createStandings, 
      case cs.PlayerStatSortOrder when 'value' then 'True' else 'False' end as createStats,
      py_matchdaysType as matchdaysType, -- Spieltag, Turnier, Runde, Gruppe
      py_matchdaysSortedBy as matchdaysSortedBy, -- Startdatum, Name
      -- min(date(g.StartDate)) as startDate,
      -- max(date(g.StartDate)) as endDate,
      min(g.StartDate) as startDate,
      max(g.StartDate) as endDate,
      json_object(
        'numOfPeriods', cs.NumOfPeriods,
        'periodLengthMin', cs.PeriodLength,
        'overtime', case when cs.IsOvertime = 1 then 'True' else 'False' end,
        'numOfPeriodsOvertime', cs.NumOfPeriodsOT,
        'periodLengthMinOvertime', cs.PeriodLengthOT,
        'shootout', case when cs.IsShootout = 1 then 'True' else 'False' end,
        'refereePoints', cs.RefereePoints
      ) as matchSettings,
      'True' as published,
      cs.CreateTableByRound
    from tblteamchampionship tcs
    join tblchampionship cs on tcs.id_fk_Championship=cs.id_tblChampionship
    join tblgame g on tcs.SeasonYear=g.SeasonYear and cs.id_tblChampionship=g.id_fk_Championship
    where 1=1
    and tcs.SeasonYear in (2022, 2023)
    and cs.IsExtern=0
    and cs.id_fk_AgeGroup>0
    group by tcs.SeasonYear, cs.py_code, cs.py_round, cs.CreateTable, cs.CreateTableByRound  
  ORDER BY 1,2,3


-- get MATCHDAYS data
select
	g.SeasonYear as s_alias,
  cs.py_t_alias as t_alias,
  cs.py_round_alias as r_alias,
  COALESCE(g.Round, 'ALL_GAMES') as name,
  COALESCE(g.py_md_alias, 'all_games') as alias,
  json_object(
    'key', case when cs.py_round = 'Playoffs' then 'PLAYOFFS' else 'REGULAR' end,
    'value', case when cs.py_round = 'Playoffs' then 'Playoffs' else 'Regulär' end
  ) as type,
  -- date(min(g.startdate)) as startDate,
  -- date(max(g.startdate)) as endDate,
  min(g.startdate) as startDate,
  max(g.startdate) as endDate,
  json_object(
    'numOfPeriods', cs.NumOfPeriods,
    'periodLengthMin', cs.PeriodLength,
    'overtime', case when cs.IsOvertime = 1 then 'True' else 'False' end,
    'numOfPeriodsOvertime', cs.NumOfPeriodsOT,
    'periodLengthMinOvertime', cs.PeriodLengthOT,
    'shootout', case when cs.IsShootout = 1 then 'True' else 'False' end,
    'refereePoints', cs.RefereePoints
  ) as matchSettings,
  -- case cs.CreateTable when 1 then 'True' else 'False' end as createStandings, 
  -- case cs.PlayerStatSortOrder when 'value' then 'True' else 'False' end as createStats,
  case when g.py_md_alias  like 'gruppe%' then 'True' else 'False' end as createStandings,
  'False' as createStats,
  'True' as published
from tblgame as g
join tblchampionship as cs on g.id_fk_Championship=cs.id_tblChampionship
where g.SeasonYear in (2022,2023)
and cs.id_tblchampionship not in (-1, 46)
and id_fk_gamestatus in (2,4)
group by g.SeasonYear,cs.id_tblchampionship,cs.name,cs.py_code,cs.py_round,g.Round
order by g.seasonYear, cs.py_code, cs.py_round, g.round, cs.CreateTableByRound


  
-- alias
  update `tblgame` 
  set py_md_alias=
    replace(
      replace(
        replace(
          replace(  
            replace(
              replace(
                replace(lower(trim(coalesce(Round, 'ALL_GAMES')), ' ', '-')
                , 'ü', 'ue')
            , 'ö', 'oe')
          , 'ä' ,'ae')
        , 'ß', 'ss')
      , '`', '-')
    , '.', '')
   where SeasonYear in (2022, 2023)

-- fix matchdays (youth leagues)
-- mini: 45
SELECT seasonyear, id_fk_Championship, MatchDay, week, Round, StartDate,s.id_tblstadium, s.Name, s.shortname
FROM tblgame g
join tblstadium s on g.id_fk_Stadium=s.id_tblStadium
where id_fk_championship in (45)
and g.seasonyear=2022
order by seasonyear desc, startdate
--- 2023: week: 1,7,12,25
update tblgame set round='Red Devils'
  where id_fk_championship=45 and seasonyear=2023
  and week=7;
update tblgame set round='Berlin Buffalos 2'
  where id_fk_championship=45 and seasonyear=2023
  and week=25;

-- sl: 10,43,44
where id_fk_championship in (10,43,44)
SELECT g.SeasonYear, g.id_fk_Championship, g.Round, date(g.StartDate), count(*)
  from tblgame g
  where SeasonYear=2022 and id_fk_Championship in (10,43,44)
  group by g.SeasonYear, g.id_fk_Championship, g.Round, date(g.StartDate)
  order by 1,2,3,4
--- fix:
  update tblgame g
    inner join tblstadium s on g.id_fk_Stadium=s.id_tblStadium
    set g.round=s.shortname
    where id_fk_championship in (10,43,44)
    and g.seasonyear=2022
  update tblgame g
    set round = concat(round, ' 2')
    where id_fk_championship in (10,43,44)
    and g.seasonyear=2022 
    and week in (8)

-- jgl: 35,47,48
SELECT seasonyear, id_fk_Championship, MatchDay, week, Round, StartDate,s.id_tblstadium, s.Name, s.shortname
FROM tblgame g
join tblstadium s on g.id_fk_Stadium=s.id_tblStadium
where id_fk_championship in (35,47,48)
and g.seasonyear=2023
and id_fk_gamestatus in (2,4)
order by seasonyear desc, startdate;

SELECT g.SeasonYear, g.id_fk_Championship, g.Round, date(g.StartDate), count(*)
  from tblgame g
  where SeasonYear=2022 and id_fk_Championship in (35,47,48)
  and id_fk_gamestatus in (2,4)
  group by g.SeasonYear, g.id_fk_Championship, g.Round, date(g.StartDate)
  order by 1,2,3,4
--- fix:
  update tblgame g
    inner join tblstadium s on g.id_fk_Stadium=s.id_tblStadium
    set g.round=s.shortname
    where id_fk_championship in (35,47,48)
    and g.seasonyear=2023
  update tblgame g
    set round = concat(round, ' 2')
    where id_fk_championship in (35,47,48)
    and g.seasonyear=2022 
    and week in (11,13,17)

-- jnl: 26
SELECT seasonyear, id_fk_Championship, MatchDay, week, Round, StartDate,s.id_tblstadium, s.Name, s.shortname
FROM tblgame g
join tblstadium s on g.id_fk_Stadium=s.id_tblStadium
where id_fk_championship in (26)
and g.seasonyear=2023
and id_fk_gamestatus in (2,4)
order by seasonyear desc, startdate;
-- fix:
  update tblgame g
    inner join tblstadium s on g.id_fk_Stadium=s.id_tblStadium
    set g.round=s.shortname
    where id_fk_championship in (26)
    and g.seasonyear=2023



-- fix mtchdays settings, which come from tblgeme
    SELECT 
    code, name,
    py_name, py_round, py_md_type,
    IsOvertime, IsShootout,
    PointsWinReg, PointsTie, PointsWinOT, PointsWinSO
    FROM tblchampionship cs  
    ORDER BY `cs`.`py_name` ASC

