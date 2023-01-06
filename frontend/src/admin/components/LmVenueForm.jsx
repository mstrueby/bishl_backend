import React from 'react'
import { Formik, Form } from 'formik'
import * as Yup from 'yup'
import InputText from './form/InputText'
import ButtonPrimary from './form/ButtonPrimary'
import ButtonLight from './form/ButtonLight'
import Toggle from './form/Toggle'
import { Switch } from '@headlessui/react'
import { useState } from 'react';


const LmVenueForm = ({
    initialValues,
    onSubmit,
    enableReinitialize,
    handleCancel,
}) => {
    const [enabled, setEnabled] = useState(false)
    
    return (
        <>
            <Formik
                initialValues={initialValues}
                enableReinitialize={enableReinitialize}
                validationSchema={Yup.object({
                    name: Yup.string()
                        .max(30, 'Nicht mehr als 30 Zeichen')
                        .required('Name ist ein Pflichtfeld'),
                    shortName: Yup.string()
                        .max(15, 'Nicht mehr als 30 Zeichen')
                        .required('Kurzname ist ein Pflichtfeld')
                })}
                onSubmit={onSubmit}
            >
                <Form>
                    <InputText
                        name="name"
                        type="text"
                        label="Name"
                    />
                    <InputText
                        name="shortName"
                        type="text"
                        label="Kurzname"
                    />
                    <InputText
                        name="street"
                        type="text"
                        label="Straße"
                    />
                    <InputText
                        name="zipCode"
                        type="text"
                        label="PLZ"
                    />
                    <InputText
                        name="city"
                        type="text"
                        label="Stadt"
                    />
                    <InputText
                        name="country"
                        type="text"
                        label="Land"
                    />
                    <InputText
                        name="latitude"
                        type="number"
                        label="Latitude"
                    />
                    <InputText
                        name="longitude"
                        type="number"
                        label="Longitude"
                    />
                    
                    {/* <InputText
                        name="active"
                        type="checkbox"
                        label="Aktiv"
                    /> */}
                    <Toggle 
                        name="active"
                        type="checkbox"
                        label="Aktiv"
                    />

{/* <Switch
            // {...field} {...props}
            value="true"
            name="active"
            checked={enabled}
            onChange={setEnabled}
            className={classNames(
                enabled ? 'bg-indigo-600' : 'bg-gray-200',
                'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2'
            )}
        >
            <span className="sr-only">Use setting</span>
            <span
                aria-hidden="true"
                className={classNames(
                    enabled ? 'translate-x-5' : 'translate-x-0',
                    'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out'
                )}
            />
        </Switch> */}


                    <ButtonPrimary
                        name="btnPrimary"
                        type="submit"
                        children="Speichern"
                        />
                    <ButtonLight
                        name="btnLight"
                        type="button"
                        onClick={handleCancel}
                        children="Abbrechen"
                    />
                </Form>

            </Formik>
        </>
    )
}

function classNames(...classes) {
    return classes.filter(Boolean).join(' ')
}

export default LmVenueForm