import React from 'react'
import { useFormik} from 'formik'
// import { getFormItemValidateStatus, getFormItemError } from "../../utils"

const LmClubForm = ({
    initialValues,
    validate, // or validateSchema,
    onSubmit,
    enableReinitialize,
    handleCancel,
    isNew
}) => {
    const formik = useFormik({
        initialValues,
        validate,
        onSubmit,
        enableReinitialize,
        // validateSchema
    });

    const {
        handleSubmit,
        values,
        errors,
        getFieldProps,
        getFieldValue,
        setFieldValue,
        handleBlur,
        dirty,
        isValid,
        isSubmitting
    } = formik;

    return (
        <form onSubmit={formik.handleSubmit}>
            <label htmlFor='text'>Name</label>
            <input
                id="name"
                name="name"
                type="text"
                onChange={formik.handleChange}
                onBlur={formik.handleBlur}
                value={formik.values.name}
            />
            {formik.touched.name && formik.errors.name ? <div>{formik.errors.name}</div> : null}

            <label htmlFor='text'>Anschrift (c/o)</label>
            <input
                id="addressName"
                name="addressName"
                type="text"
                onChange={formik.handleChange}
                onBlur={formik.handleBlur}
                value={formik.values.addressName}
            />
            {formik.touched.addressName && formik.errors.addressName ? <div>{formik.errors.addressName}</div> : null}
            
            <label htmlFor='text'>Straße</label>
            <input
                id="street"
                name="street"
                type="text"
                onChange={formik.handleChange}
                onBlur={formik.handleBlur}
                value={formik.values.street}
            />
            {formik.touched.street && formik.errors.street ? <div>{formik.errors.street}</div> : null}
            
            <label htmlFor='text'>PLZ</label>
            <input
                id="zipCode"
                name="zipCode"
                type="number"
                onChange={formik.handleChange}
                onBlur={formik.handleBlur}
                value={formik.values.zipCode}
            />
            {formik.touched.zipCode && formik.errors.zipCode ? <div>{formik.errors.zipCode}</div> : null}
            
            <label htmlFor='text'>Stadt</label>
            <input
                id="city"
                name="city"
                type="text"
                onChange={formik.handleChange}
                onBlur={formik.handleBlur}
                value={formik.values.city}
            />
            {formik.touched.city && formik.errors.city ? <div>{formik.errors.city}</div> : null}
            
            <label htmlFor='text'>Land</label>
            <input
                id="country"
                name="country"
                type="text"
                onChange={formik.handleChange}
                onBlur={formik.handleBlur}
                value={formik.values.country}
            />
            {formik.touched.country && formik.errors.country ? <div>{formik.errors.country}</div> : null}
            
            <label htmlFor='text'>Gründungsjahr</label>
            <input
                id="dateOfFoundation"
                name="dateOfFoundation"
                type="text"
                onChange={formik.handleChange}
                onBlur={formik.handleBlur}
                value={formik.values.dateOfFoundation}
            />
            {formik.touched.dateOfFoundation && formik.errors.dateOfFoundation ? <div>{formik.errors.dateOfFoundation}</div> : null}
            
            <label htmlFor='text'>Website</label>
            <input
                id="website"
                name="website"
                type="text"
                onChange={formik.handleChange}
                onBlur={formik.handleBlur}
                value={formik.values.website}
            />
            {formik.touched.website && formik.errors.website ? <div>{formik.errors.website}</div> : null}
            
            <label htmlFor='text'>ISHD-ID</label>
            <input
                id="ishdId"
                name="ishdId"
                type="number"
                onChange={formik.handleChange}
                onBlur={formik.handleBlur}
                value={formik.values.ishdId}
            />
            {formik.touched.ishdId && formik.errors.ishdId ? <div>{formik.errors.ishdId}</div> : null}
            
            <label htmlFor='text'>Aktiv</label>
            <input
                id="active"
                name="active"
                type="text"
                onChange={formik.handleChange}
                onBlur={formik.handleBlur}
                value={formik.values.active}
            />

            <button type="submit">Speichern</button>
            <button type="button" onClick={handleCancel}>Abbrechen</button>
        </form>
    )
}

export default LmClubForm