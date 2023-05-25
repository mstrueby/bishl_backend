import React from 'react'
import { Formik, Form } from 'formik'
import * as Yup from 'yup'
import InputText from './form/InputText'
import ButtonPrimary from './form/ButtonPrimary'
import ButtonLight from './form/ButtonLight'
import Toggle from './form/Toggle'
import MyListbox from './form/Listbox'

const countries = [
    { key: 'DE', value: 'Deutschland' },
    { key: 'CH', value: 'Schweiz' },
    { key: 'AT', value: 'Österreich' },
    { key: 'DK', value: 'Dänemark' },
    { key: 'GB', value: 'Großbritannien' }
]

const LmVenueForm = ({
    initialValues,
    onSubmit,
    enableReinitialize,
    handleCancel,
}) => {

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
                    <MyListbox
                        name="country"
                        options={countries}
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
                    <Toggle
                        name="active"
                        type="checkbox"
                        label="Aktiv"
                    />
                    <div className="mt-4 flex justify-end py-4 px-4 sm:px-6">
                        <ButtonLight
                            name="btnLight"
                            type="button"
                            onClick={handleCancel}
                            children="Abbrechen"
                        />
                        <ButtonPrimary
                            name="btnPrimary"
                            type="submit"
                            children="Speichern"
                        />
                    </div>
                </Form>
            </Formik>
        </>
    )
}

export default LmVenueForm