import React from 'react'
import { useFormik} from 'formik'
// import { getFormItemValidateStatus, getFormItemError } from "../../utils"

const LmVenueForm = ({
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

            <label htmlFor='text'>Kurzname</label>
            <input
                id="shortName"
                name="shortName"
                type="text"
                onChange={formik.handleChange}
                onBlur={formik.handleBlur}
                value={formik.values.shortName}
            />
            {formik.touched.shortName && formik.errors.shortName ? <div>{formik.errors.shortName}</div> : null}
            
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
            
            <label htmlFor='text'>Latitude</label>
            <input
                id="latitude"
                name="latitude"
                type="number"
                onChange={formik.handleChange}
                onBlur={formik.handleBlur}
                value={formik.values.latitude}
            />
            {formik.touched.latitude && formik.errors.latitude ? <div>{formik.errors.latitude}</div> : null}
            
            <label htmlFor='text'>Longitude</label>
            <input
                id="longitude"
                name="longitude"
                type="number"
                onChange={formik.handleChange}
                onBlur={formik.handleBlur}
                value={formik.values.longitude}
            />
            {formik.touched.longitude && formik.errors.longitude ? <div>{formik.errors.longitude}</div> : null}
            
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

export default LmVenueForm