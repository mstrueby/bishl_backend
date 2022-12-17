import React from 'react'
import LmSidebar from '../components/LmSidebar'
import Layout from '../../components/Layout'


const LmDashboard = () => {
    return (
        <Layout>
            <div>
                <LmSidebar/>
            </div>
            <div><h2>Spielbetrieb - Dashboard</h2></div>
        </Layout>
    )
}

export default LmDashboard