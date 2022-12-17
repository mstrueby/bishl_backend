import { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from "react-router-dom"
import AdmLayout from '../../components/AdmLayout'
import { CheckCircleIcon, XMarkIcon } from '@heroicons/react/20/solid'

// import navigation from './LeagueManager'

const LmVenues = () => {
  const [venues, setVenues] = useState([])
  const [show, setShow] = useState(true)
  const location = useLocation();
  const navigate = useNavigate();


  let msg = location.state ? location.state.message : null;

  const routeChange = () => {
    let path = `/admin/venues/new`;
    navigate(path);
  }

  useEffect(() => {
    fetch(`http://localhost:8000/venues`)
      .then(response => response.json())
      .then(json => { setVenues(json) })
  }, [])

  return (
    <AdmLayout>

      <div className="border-b border-gray-200 pb-5 sm:flex sm:items-center sm:justify-between">
        <h3 className="text-lg font-medium leading-6 text-gray-900">Spielstätten</h3>
        <div className="mt-3 sm:mt-0 sm:ml-4">
          <button
            type="button"
            className="inline-flex items-center rounded-md border border-transparent bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
            onClick={routeChange}
          >
            Neu
          </button>
        </div>
      </div>

      {(show ===true && msg) &&
        // <div className="rounded-md bg-green-50 p-4 my-6">
        <div className="rounded-md border-l-4 border-green-400 bg-green-50 p-4 my-6">
          <div className="flex">
            <div className="flex-shrink-0">
              <CheckCircleIcon className="h-5 w-5 text-green-400" aria-hidden="true" />
            </div>
            <div className="ml-3">
              <p className="text-sm font-medium text-green-800">{msg}</p>
            </div>
            <div className="ml-auto pl-3">
              <div className="-mx-1.5 -my-1.5">
                <button
                  type="button"
                  className="inline-flex rounded-md bg-green-50 p-1.5 text-green-500 hover:bg-green-100 focus:outline-none focus:ring-2 focus:ring-green-600 focus:ring-offset-2 focus:ring-offset-green-50"
                  onClick={() => setShow(false)}
                >
                  <span className="sr-only">Schließen</span>
                  <XMarkIcon className="h-5 w-5" aria-hidden="true" />
                </button>
              </div>
            </div>
          </div>
        </div>
      }

      <div className="mt-8 flex flex-col">
        <div className="-my-2 -mx-4 overflow-x-auto sm:-mx-6 lg:-mx-8">
          <div className="inline-block min-w-full py-2 align-middle md:px-6 lg:px-8">
            <div className="overflow-hidden shadow ring-1 ring-black ring-opacity-5 md:rounded-lg">
              <table className="min-w-full divide-y divide-gray-300">
                <thead className="bg-gray-50">
                  <tr>
                    <th scope="col" className="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-6">
                      Spielstätte
                    </th>
                    <th scope="col" className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900 text-center">
                      Status
                    </th>
                    <th scope="col" className="relative py-3.5 pl-3 pr-4 sm:pr-6">
                      <span className="sr-only">Edit</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 bg-white">

                  {venues && venues.map(
                    (venue) => {
                      return (

                        <tr key={venue.name}>
                          <td className="whitespace-nowrap py-4 pl-4 pr-3 text-sm sm:pl-6">
                            <div className="flex items-center">
                              {/* <div className="h-10 w-10 flex-shrink-0">
                            <img className="h-10 w-10 rounded-full" src={person.image} alt="" />
                          </div> */}
                              <div className="">
                                <div className="font-medium text-gray-900">{venue.name}</div>
                                <div className="text-gray-500">{venue.street}, {venue.zipCode} {venue.city}</div>
                              </div>
                            </div>
                          </td>
                          <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500 text-center">
                            {venue.active === true ? (
                                <span className="inline-flex rounded-full bg-green-100 px-2 text-xs font-semibold leading-5 text-green-800">
                                  Aktiv
                                </span>
                              ) : (
                                <span className="inline-flex items-center rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800">
                                  Inaktiv
                                </span>
                              )
                            }
                          </td>
                          <td className="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-6">
                            <Link to={`/admin/venues/${venue._id}`}>
                              <p className="text-indigo-600 hover:text-indigo-900">
                                Bearbeiten<span className="sr-only">, {venue.name}</span>
                              </p>
                            </Link>
                          </td>
                        </tr>
                      )
                    }
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>




    </AdmLayout >

  )
}

export default LmVenues