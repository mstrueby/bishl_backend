export const clubValidator = (values) => {
    const errors = {};
    if (!values.name) {
        errors.name = 'Pflichtfeld Name'
    }
    else if (values.name.length > 50) {
        errors.name = 'Nicht mehr als 50 Zeichen';
    }

    if (!values.country) {
        errors.country = 'Pflichtfeld Land';
    } 

    return errors;
  }