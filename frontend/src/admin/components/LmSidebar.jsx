import React from 'react'
import Sidebar from '../components/Sidebar'
import { TrophyIcon, QueueListIcon, CalendarIcon, CalendarDaysIcon, RectangleStackIcon, BookmarkIcon, RectangleGroupIcon, UserIcon, UserGroupIcon } from '@heroicons/react/24/outline'

const navigation = [
    { name: 'Dashboard', icon: RectangleGroupIcon, href: '/admin/leaguemanager', current: false },
    { name: 'Vereine', icon: BookmarkIcon, href: '/admin/clubs', current: false },
    { name: 'Mannschaften', icon: UserGroupIcon, href: '/admin/teams', current: false },
    { name: 'Spieler', icon: UserIcon, href: '/', current: false },
    { name: 'Spielflächen', icon: RectangleStackIcon, href: '/admin/venues', current: false },
    { name: 'Wettbewerbe', icon: TrophyIcon, href: '/', current: false },
    { name: 'Saisons', icon: CalendarIcon, href: '/', current: false },
    { name: 'Spieltage', icon: CalendarDaysIcon, href: '/', current: false },
    { name: 'Spiele', icon: QueueListIcon, href: '/', current: false },
]

const LmSidebar = () => {
    return (
        <Sidebar navigation={navigation} />
    )
}

export default LmSidebar