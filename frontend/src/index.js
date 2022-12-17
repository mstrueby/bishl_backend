import React from 'react';
import ReactDOM from 'react-dom/client';
import {
  BrowserRouter, 
  Routes, 
  Route,
} from "react-router-dom";

import Venue from './pages/Venue'
import Venues from './pages/Venues'
import LmDashboard from './admin/pages/LmDashboard';

import LmClubList from './admin/pages/LmClubList'
import LmClubEdit from './admin/pages/LmClubEdit'
import LmClubNew from './admin/pages/LmClubNew'
import LmVenueList from './admin/pages/LmVenueList'
import LmVenueEdit from './admin/pages/LmVenueEdit'
import LmVenueNew from './admin/pages/LmVenueNew'


import './index.css';
import App from './App';
import reportWebVitals from './reportWebVitals';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="venues" element={<Venues />} />
        <Route path="venues/:id" element={<Venue />} />
        
        <Route path="admin/leaguemanager" element={<LmDashboard />} />

        <Route path="admin/clubs" element={<LmClubList />} />
        <Route path="admin/clubs/:id" element={<LmClubEdit />} />
        <Route path="admin/clubs/new" element={<LmClubNew />} />

        <Route path="admin/venues" element={<LmVenueList />} />
        <Route path="admin/venues/:id" element={<LmVenueEdit />} />
        <Route path="admin/venues/new" element={<LmVenueNew />} />

      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();
