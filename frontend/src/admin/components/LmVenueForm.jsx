import React from 'react'
import { Formik, Form } from 'formik'
import * as Yup from 'yup'
import InputText from './form/InputText'
import ButtonPrimary from './form/ButtonPrimary'
import ButtonLight from './form/ButtonLight'
import Toggle from './form/Toggle'
import MyListbox from './form/Listbox'

const countries = [
    { name: 'Deutschland', code: 'DE', value: 'DE' },
    { name: 'Schweiz', code: 'CH', value: 'CH' },
    { name: 'Österreich', code: 'AT', value: 'AT' },
    { name: 'Dänemark', code: 'DK', value: 'DK' },
    { name: 'Großbritannien', code: 'GB', value: 'GB' }
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

export default LmVenueForm