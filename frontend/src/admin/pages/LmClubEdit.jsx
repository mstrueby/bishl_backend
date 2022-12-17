import { useState, useEffect } from 'react'
import { useParams, useNavigate } from "react-router-dom"
import LmClubForm from "../components/LmClubForm";
import { clubValidator } from "../clubValidators";
import Layout from '../../components/Layout';
import LmSidebar from '../components/LmSidebar'

let BASE_URL = "http://localhost:8000/clubs/"

const LmClubEdit = () => {

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
    <Layout>
      <main className="relative">
        <div className="mx-auto max-w-screen-xl pb-6 lg:pb-16">
          <div className="overflow-hidden bg-white">
            <div className="divide-y divide-gray-200 md:grid md:grid-cols-12 md:divide-y-0 md:divide-x">
              <LmSidebar />
              <div className="px-4 md:px-8 py-6 md:col-span-9">
                <h2>Verein ändern</h2>
                <LmClubForm {...formProps} />
              </div>
            </div>
          </div>
        </div>
      </main>
    </Layout >
  );
}

export default LmClubEdit