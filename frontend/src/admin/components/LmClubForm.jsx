import React from 'react'
import { Formik, Form } from 'formik'
import * as Yup from 'yup'
import InputText from './form/InputText'
import ButtonPrimary from './form/ButtonPrimary'
import ButtonLight from './form/ButtonLight'
import Toggle from './form/Toggle'
import MyListbox from './form/Listbox'

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
                        label="Name"
                        name="name"
                        type="text"
                    />
                    <InputText
                        label="Anschrift (c/o)"
                        name="addressName"
                        type="text"
                    />
                    <InputText
                        label="Straße"
                        name="street"
                        type="text"
                    />
                    <InputText
                        label="PLZ"
                        name="zipCode"
                        type="text"
                    />
                    <InputText
                        label="City"
                        name="city"
                        type="text"
                    />
                    <MyListbox
                        label="Land"
                        name="country"
                        type=""
                    />
                    <Toggle
                        name="active"
                        label="Aktiv"
                        type="checkbox"
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