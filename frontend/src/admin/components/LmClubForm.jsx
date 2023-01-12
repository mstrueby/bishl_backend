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

const LmClubForm = ({
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
                        .max(50, 'Nicht mehr als 50 Zeichen')
                        .required('Name ist Pflichtfeld')
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
                        name="addressName"
                        type="text"
                        label="Anschrift (c/o)"
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
                        label="City"
                    />
                    <MyListbox
                        name="country"
                        options={countries}
                        label="Land"
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

export default LmClubForm