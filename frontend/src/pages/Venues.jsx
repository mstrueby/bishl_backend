import {useState, useEffect} from 'react'
import Layout from '../components/Layout'
import Card from '../components/Card'


const Venues = () => {
  const [venues, setVenues] = useState([])

  useEffect(() => {
    fetch(`http://localhost:8000/venues`)
      .then(response=>response.json())
      .then(json=>{setVenues(json)})
  },[])

  return (
    <Layout>
      <h2>Spielstätten</h2>
      <div>
        <div>
          {venues && venues.map(
            (el)=>{
              return (<Card key={el._id} venue = {el} />)
            }
          )}
        </div>
      </div>
    </Layout>

  )
}

export default Venues