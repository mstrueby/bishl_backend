import React from 'react'
import LmSidebar from '../components/LmSidebar'
import Layout from '../../components/Layout'
import Backend from '../../components/Backend'


const LmDashboard = () => {
    return (
        <Layout>
            <Backend
                sidebar={<LmSidebar />}
                content={<Content />}
            />
        </Layout>
    )
}

const Content = () => {
    <h2>Spielbetrieb - Dashboard</h2>
}

export default LmDashboard