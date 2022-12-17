export const getFormItemError = (formik, field, onlyTouched = true) => {
    const { errors, touched } = formik;
    if (onlyTouched) {
      return errors[field] && touched[field] ? errors[field] : null;
    }
    return errors[field] ? errors[field] : null;
  };
  
  export const getFormItemValidateStatus = (formik, field, onlyTouched) => {
    return getFormItemError(formik, field, onlyTouched) ? "error" : "";
  };
  
  export const wait = async (timeout = 3000) =>
    new Promise((res) => setTimeout(() => res(), timeout));
  