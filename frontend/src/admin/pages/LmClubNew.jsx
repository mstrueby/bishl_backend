import { useState } from 'react'
import LmClubForm from "../components/LmClubForm";
import { clubValidator } from "../clubValidators";
import { useNavigate } from 'react-router-dom';
import Layout from '../../components/Layout'
import Backend from '../../components/Backend';
import LmSidebar from '../components/LmSidebar'

let BASE_URL = "http://localhost:8000/clubs/"

const LmClubNew = () => {
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
    addressName: '',
    street: '',
    zipCode: '',
    city: '',
    country: '',
    email: '',
    dateOfFoundation: '',
    website: '',
    ishdId: '',
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
      navigate("/admin/clubs", { state: { message: "Verein erfolgreich angelegt." } });
    }
  };

  const validate = (values) => {
    const errors = clubValidator(values);
    return errors;
  };

  const handleCancel = () => {
    navigate('/admin/clubs')
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
        <h2 className="text-lg font-medium leading-6 text-gray-900">Neuer Verein</h2>
      </div>
      <div>
        <LmClubForm {...formProps} />
      </div>
    </div >
  );
}

export default LmClubNew