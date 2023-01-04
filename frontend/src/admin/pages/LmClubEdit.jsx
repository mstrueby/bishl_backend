import { useState, useEffect } from 'react'
import { useParams, useNavigate } from "react-router-dom"
import LmClubForm from "../components/LmClubForm"
import { clubValidator } from "../clubValidators"
import Layout from '../../components/Layout'
import Backend from '../../components/Backend'
import LmSidebar from '../components/LmSidebar'

let BASE_URL = "http://localhost:8000/clubs/"

const LmClubEdit = () => {
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

  let { id } = useParams()
  const [club, setClub] = useState({})
  const [error, setError] = useState([])
  const navigate = useNavigate();

  const initialValues = { ...club }

  const onSubmit = async (values, actions) => {
    const response = await fetch(`${BASE_URL}${id}`, {
      method: "PATCH",
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
      navigate("/admin/clubs", { state: { message: "Verein erfolgreich gespeichert" } });
    }

    //actions.setSubmitting(false);
    //actions.setStatus({message: response.data.message});

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
    validate,
    onSubmit,
    enableReinitialize: true,
    handleCancel,
    isNew: false,
  };

  useEffect(() => {
    async function getClub() {
      const res = await fetch(`${BASE_URL}${id}`)
      if (!res.ok) {
        setError("Error fetching club")
      } else {
        const data = await res.json()
        setClub(data)
      }
    }
    getClub();
    // setIsPending(false)
  }, [id])

  return (
    <div>
      <div className="border-b border-gray-200 pb-5 sm:flex sm:items-center sm:justify-between">
        <h2 className="text-lg font-medium leading-6 text-gray-900">Verein bearbeiten</h2>
      </div>
      <div>
        <LmClubForm {...formProps} />
      </div>
    </div >
  );
}

export default LmClubEdit