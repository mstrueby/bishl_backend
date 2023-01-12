import { useState } from 'react'
import LmVenueForm from "../components/LmVenueForm";
import { venueValidator } from "../venueValidators";
import { useNavigate } from 'react-router-dom';
import AdmLayout from '../../components/Backend';
import Layout from '../../components/Layout'
import Backend from '../../components/Backend';
import LmSidebar from '../components/LmSidebar'

let BASE_URL = "http://localhost:8000/venues/"

const LmVenueNew = () => {
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
  const [error, setError] = useState([])
  const navigate = useNavigate();

  const initialValues = {
    name: '',
    shortName: '',
    street: '',
    zipCode: '',
    city: '',
    country: '',
    latitude: '',
    longitude: '',
    active: false,
  };

  const onSubmit = async (values, actions) => {

    const response = await fetch(BASE_URL, {
      method: "POST",
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(values)
    })

    const data = await response.json()

    if (!response.ok) {
      let errArray = data.detail.map(el => {
        return `${el.loc[1]} -${el.msg}`
      })
      setError(errArray)
    } else {
      setError([])
      navigate("/admin/venues", { state: { message: "Spielstätte erfolgreich angelegt." } });
    }
  };

  const validate = (values) => {
    const errors = venueValidator(values);
    return errors;
  };

  const handleCancel = () => {
    navigate('/admin/venues')
  }

  const formProps = {
    initialValues,
    validate, // or validationSchema. Check example validation schema in validators.js file
    onSubmit,
    enableReinitialize: false,
    handleCancel,
    isNew: true,
  };

  return (
    <div>
      <div className="border-b border-gray-200 pb-5 sm:flex sm:items-center sm:justify-between">
        <h2 className="text-lg font-medium leading-6 text-gray-900">Neue Spielfläche</h2>
      </div>
      <div>
        <LmVenueForm {...formProps} />
      </div>
    </div >
  );
}

export default LmVenueNew